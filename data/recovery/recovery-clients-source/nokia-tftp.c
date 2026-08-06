typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef unsigned long u64;
typedef long ssize_t;
typedef unsigned long size_t;
typedef unsigned int socklen_t;

extern int socket(int,int,int);
extern int setsockopt(int,int,int,const void*,socklen_t);
extern ssize_t sendto(int,const void*,size_t,int,const void*,socklen_t);
extern ssize_t recvfrom(int,void*,size_t,int,void*,socklen_t*);
extern int close(int);
extern int open(const char*,int,...);
extern ssize_t write(int,const void*,size_t);
extern size_t strlen(const char*);

#define AF_INET 2
#define SOCK_DGRAM 2
#define IPPROTO_UDP 17
#define SOL_SOCKET 1
#define SO_RCVTIMEO 20
#define O_WRONLY 1
#define O_CREAT 0100
#define O_TRUNC 01000

struct timeval { long tv_sec; long tv_usec; };
struct sockaddr_in { u16 sin_family; u16 sin_port; u32 sin_addr; u8 sin_zero[8]; };

static u8 pkt[8192 + 64];
static u8 lastpkt[8192 + 64];
static char numbuf[16];

static u16 bswap16(u16 x) { return (u16)((x << 8) | (x >> 8)); }
static void put16(u8 *p, u16 v) { p[0]=(u8)(v>>8); p[1]=(u8)v; }
static u16 get16(const u8 *p) { return (u16)(((u16)p[0]<<8)|p[1]); }
static int streq(const char *a,const char *b) { while(*a && *a==*b){a++;b++;} return *a==0 && *b==0; }
static void copyb(u8 *d,const u8 *s,size_t n){ while(n--) *d++=*s++; }
static void copyc(u8 *d,const char *s,size_t n){ while(n--) *d++=(u8)*s++; }
static void msg(const char *s){ write(2,s,strlen(s)); }
static unsigned dec(const char *s){ unsigned v=0; if(!s||!*s) return 0; while(*s>='0'&&*s<='9'){v=v*10+(unsigned)(*s-'0');s++;} return *s?0:v; }
static int ipv4(const char *s,u32 *out){
    u32 v=0; unsigned part=0,count=0; int have=0;
    while(1){
        char c=*s++;
        if(c>='0'&&c<='9'){ part=part*10+(unsigned)(c-'0'); if(part>255) return -1; have=1; }
        else if(c=='.'||c==0){ if(!have||count>3) return -1; v |= (u32)part << (count*8); count++; part=0; have=0; if(c==0) break; }
        else return -1;
    }
    if(count!=4) return -1; *out=v; return 0;
}
static int appendz(u8 *b,int p,const char *s,int max){ int n=(int)strlen(s); if(p+n+1>max) return -1; copyc(b+p,s,(size_t)n); b[p+n]=0; return p+n+1; }
static const char *utoa10(unsigned v){ int i=15; numbuf[i]=0; do{numbuf[--i]=(char)('0'+v%10);v/=10;}while(v); return &numbuf[i]; }
static int write_all(int fd,const u8 *b,size_t n){ while(n){ ssize_t w=write(fd,b,n); if(w<=0) return -1; b+=w;n-=(size_t)w;} return 0; }

int main(int argc,char **argv){
    const char *local=0,*remote=0,*server=0; unsigned port=69, blksize=4096; int get=0;
    for(int i=1;i<argc;i++){
        if(streq(argv[i],"-g")){get=1;}
        else if(streq(argv[i],"-l") && i+1<argc){local=argv[++i];}
        else if(streq(argv[i],"-r") && i+1<argc){remote=argv[++i];}
        else if(streq(argv[i],"-b") && i+1<argc){blksize=dec(argv[++i]);}
        else if(argv[i][0]=='-'){ msg("tftp: unsupported option\n"); return 2; }
        else if(!server){server=argv[i];}
        else {port=dec(argv[i]);}
    }
    if(!get||!local||!remote||!server||port==0||blksize<512||blksize>8192){
        msg("usage: tftp -g -l LOCAL -r REMOTE [-b BLOCK] SERVER [PORT]\n"); return 2;
    }
    int outfd;
    if(streq(local,"-")) outfd=1; else { outfd=open(local,O_WRONLY|O_CREAT|O_TRUNC,0600); if(outfd<0){msg("tftp: cannot open output\n");return 3;} }
    int fd=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP); if(fd<0){msg("tftp: socket failed\n");return 4;}
    struct timeval tv={5,0}; setsockopt(fd,SOL_SOCKET,SO_RCVTIMEO,&tv,(socklen_t)sizeof(tv));
    struct sockaddr_in peer; for(size_t i=0;i<sizeof(peer);i++) ((u8*)&peer)[i]=0;
    peer.sin_family=AF_INET; peer.sin_port=bswap16((u16)port); if(ipv4(server,&peer.sin_addr)<0){msg("tftp: invalid IPv4\n");return 5;}
    int p=0; put16(pkt,1); p=2; p=appendz(pkt,p,remote,sizeof(pkt)); p=appendz(pkt,p,"octet",sizeof(pkt)); p=appendz(pkt,p,"blksize",sizeof(pkt)); p=appendz(pkt,p,utoa10(blksize),sizeof(pkt));
    if(p<0){msg("tftp: request too long\n");return 6;}
    copyb(lastpkt,pkt,(size_t)p); int lastlen=p; struct sockaddr_in dest=peer; socklen_t destlen=sizeof(dest);
    if(sendto(fd,lastpkt,(size_t)lastlen,0,&dest,destlen)<0){msg("tftp: send failed\n");return 7;}
    u16 expected=1; int retries=0; int established=0; unsigned actual=512;
    for(;;){
        struct sockaddr_in src; socklen_t srclen=sizeof(src); ssize_t n=recvfrom(fd,pkt,sizeof(pkt),0,&src,&srclen);
        if(n<0){ if(++retries>12){msg("tftp: timeout\n");return 8;} sendto(fd,lastpkt,(size_t)lastlen,0,&dest,destlen); continue; }
        if(n<4) continue; u16 op=get16(pkt);
        if(!established){ dest=src; destlen=srclen; established=1; }
        if(op==5){msg("tftp: server error\n");return 9;}
        if(op==6){
            actual=blksize; put16(lastpkt,4);put16(lastpkt+2,0);lastlen=4; sendto(fd,lastpkt,4,0,&dest,destlen); retries=0; continue;
        }
        if(op!=3) continue;
        u16 block=get16(pkt+2);
        if(block==expected){
            size_t data=(size_t)n-4; if(write_all(outfd,pkt+4,data)<0){msg("tftp: output write failed\n");return 10;}
            put16(lastpkt,4);put16(lastpkt+2,block);lastlen=4; sendto(fd,lastpkt,4,0,&dest,destlen); retries=0;
            expected=(u16)(expected+1);
            if(data<actual){ if(outfd!=1) close(outfd); close(fd); return 0; }
        } else if(block==(u16)(expected-1)) { sendto(fd,lastpkt,(size_t)lastlen,0,&dest,destlen); }
    }
}
