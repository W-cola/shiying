package cn.shiying.mobile.core;

/** Java ISAAC64 byte stream for the playback parameter explicitly supplied by a Channels page.
 * Algorithm: Bob Jenkins, ISAAC64. No account token, password, key guessing or DRM handling.
 */
public final class ChannelsCodec {
    public static final int PREFIX=131072;
    private final long[] memory=new long[256],results=new long[256];
    private long accumulator,last,counter,word; private int index=255,left,consumed;
    public ChannelsCodec(String decimalKey) {
        if (decimalKey==null||!decimalKey.matches("[0-9]{1,20}")) throw new IllegalArgumentException("无效的网页播放参数。");
        results[0]=Long.parseUnsignedLong(decimalKey);
        long[] values=new long[8]; java.util.Arrays.fill(values,0x9e3779b97f4a7c13L);
        for (int i=0;i<4;i++) mix(values);
        for (int pass=0;pass<2;pass++) for (int block=0;block<256;block+=8) {
            for (int i=0;i<8;i++) values[i]+=(pass==0?results:memory)[block+i];
            mix(values); System.arraycopy(values,0,memory,block,8);
        }
        generate();
    }
    private static void mix(long[] v) {
        v[0]-=v[4];v[5]^=v[7]>>>9;v[7]+=v[0];v[1]-=v[5];v[6]^=v[0]<<9;v[0]+=v[1];
        v[2]-=v[6];v[7]^=v[1]>>>23;v[1]+=v[2];v[3]-=v[7];v[0]^=v[2]<<15;v[2]+=v[3];
        v[4]-=v[0];v[1]^=v[3]>>>14;v[3]+=v[4];v[5]-=v[1];v[2]^=v[4]<<20;v[4]+=v[5];
        v[6]-=v[2];v[3]^=v[5]>>>17;v[5]+=v[6];v[7]-=v[3];v[4]^=v[6]<<14;v[6]+=v[7];
    }
    private void generate() {
        last+=++counter;
        for (int i=0;i<256;i++) {
            switch (i&3) { case 0:accumulator=~(accumulator^(accumulator<<21));break;case 1:accumulator^=accumulator>>>5;break;case 2:accumulator^=accumulator<<12;break;default:accumulator^=accumulator>>>33; }
            accumulator+=memory[(i+128)&255]; long x=memory[i],y=memory[(int)((x>>>3)&255)]+accumulator+last;
            memory[i]=y; last=memory[(int)((y>>>11)&255)]+x; results[i]=last;
        }
    }
    private long next() { long value=results[index]; if (index--==0) { generate();index=255; } return value; }
    public void apply(byte[] data,int offset,int count) {
        if (offset<0||count<0||offset+count>data.length) throw new IllegalArgumentException("无效的媒体数据范围。");
        for (int i=0;i<count&&consumed<PREFIX;i++,consumed++) {
            if (left==0) { word=next();left=8; } data[offset+i]^=(byte)(word>>>56);word<<=8;left--;
        }
    }
}
