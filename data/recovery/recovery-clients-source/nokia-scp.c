typedef unsigned char u8;
typedef unsigned long u64;
typedef unsigned long size_t;
typedef long ssize_t;
extern int open(const char*,int,...);
extern int close(int);
extern ssize_t read(int,void*,size_t);
extern ssize_t write(int,const void*,size_t);
extern size_t strlen(const char*);
#define O_WRONLY 1
#define O_CREAT 0100
#define O_TRUNC 01000
static u8 buf[65536];
static int streq(const char*a,const char*b){while(*a&&*a==*b){a++;b++;}return *a==0&&*b==0;}
static int write_all(int fd,const void*vp,size_t n){const u8*p=(const u8*)vp;while(n){ssize_t w=write(fd,p,n);if(w<=0)return -1;p+=w;n-=(size_t)w;}return 0;}
static int ack(void){u8 z=0;return write_all(1,&z,1);}
static int fail(const char*s){u8 one=1;write_all(1,&one,1);write_all(1,s,strlen(s));write_all(1,"\n",1);return 1;}
static int read_line(char*out,int cap){int n=0;while(n<cap-1){u8 c;ssize_t r=read(0,&c,1);if(r!=1)return -1;if(c=='\n'){out[n]=0;return n;}out[n++]=(char)c;}return -1;}
static int parse_size(const char*s,u64*out,const char**after){u64 v=0;int have=0;while(*s>='0'&&*s<='9'){have=1;v=v*10+(u64)(*s-'0');s++;}if(!have||*s!=' ')return -1;*out=v;*after=s+1;return 0;}
int main(int argc,char**argv){
 const char*target=0;int sink=0;
 for(int i=1;i<argc;i++){
  if(streq(argv[i],"-t")){sink=1;continue;}
  if(streq(argv[i],"-p")||streq(argv[i],"-d")||streq(argv[i],"--"))continue;
  if(argv[i][0]=='-')continue;
  target=argv[i];
 }
 if(!sink||!target)return fail("scp sink usage error");
 if(!(target[0]=='/'&&target[1]=='t'&&target[2]=='m'&&target[3]=='p'&&target[4]=='/'))return fail("scp target must be under /tmp");
 if(ack()<0)return 2;
 char line[1024];
 for(;;){
  int n=read_line(line,sizeof(line));if(n<0)return 3;
  if(line[0]=='T'){if(ack()<0)return 4;continue;}
  if(line[0]!='C')return fail("unsupported scp command");
  if(n<8||line[5]!=' ')return fail("invalid scp header");
  u64 size=0;const char*name=0;if(parse_size(line+6,&size,&name)<0||!*name)return fail("invalid scp size");
  int fd=open(target,O_WRONLY|O_CREAT|O_TRUNC,0600);if(fd<0)return fail("cannot open scp target");
  if(ack()<0){close(fd);return 5;}
  u64 left=size;
  while(left){size_t want=left>sizeof(buf)?sizeof(buf):(size_t)left;ssize_t r=read(0,buf,want);if(r<=0){close(fd);return fail("short scp payload");}if(write_all(fd,buf,(size_t)r)<0){close(fd);return fail("scp write failed");}left-=(u64)r;}
  close(fd);
  u8 trailer=1;if(read(0,&trailer,1)!=1||trailer!=0)return fail("invalid scp trailer");
  if(ack()<0)return 6;
  return 0;
 }
}
