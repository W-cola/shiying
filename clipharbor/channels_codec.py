"""ISAAC64 stream for the playback parameter published by a Channels page.

Port of the existing Android ChannelsCodec, limited to the 128 KiB media prefix.
"""
MASK = 2**64 - 1


class ChannelsCodec:
    def __init__(self, key):
        if not str(key).isdigit() or not 0 <= int(key) <= MASK:
            raise ValueError("无效的网页播放参数。")
        self.memory, self.results = [0] * 256, [0] * 256
        self.results[0] = int(key)
        self.a = self.b = self.c = 0
        values = [0x9e3779b97f4a7c13] * 8
        for _ in range(4):
            self.mix(values)
        for source in (self.results, self.memory):
            for block in range(0, 256, 8):
                values = [(values[i] + source[block+i]) & MASK for i in range(8)]
                self.mix(values)
                self.memory[block:block+8] = values
        self.generate()
        self.index, self.left, self.word, self.consumed = 255, 0, 0, 0

    @staticmethod
    def mix(v):
        for i, shift in enumerate((9, 9, 23, 15, 14, 20, 17, 14)):
            v[i] = (v[i] - v[(i+4) % 8]) & MASK
            j, k = (i+5) % 8, (i+7) % 8
            v[j] = (v[j] ^ ((v[k] >> shift) if i % 2 == 0 else (v[k] << shift))) & MASK
            v[k] = (v[k] + v[i]) & MASK

    def generate(self):
        self.c = (self.c + 1) & MASK
        self.b = (self.b + self.c) & MASK
        for i in range(256):
            x = self.memory[i]
            if i % 4 == 0:
                self.a = ~(self.a ^ (self.a << 21)) & MASK
            elif i % 4 == 1:
                self.a ^= self.a >> 5
            elif i % 4 == 2:
                self.a = (self.a ^ (self.a << 12)) & MASK
            else:
                self.a ^= self.a >> 33
            self.a = (self.a + self.memory[(i+128) & 255]) & MASK
            y = (self.memory[(x >> 3) & 255] + self.a + self.b) & MASK
            self.memory[i] = y
            self.b = (self.memory[(y >> 11) & 255] + x) & MASK
            self.results[i] = self.b

    def apply(self, data):
        result = bytearray(data)
        for i in range(min(len(result), 131072 - self.consumed)):
            if not self.left:
                self.word, self.left = self.results[self.index], 8
                self.index -= 1
                if self.index < 0:
                    self.generate()
                    self.index = 255
            result[i] ^= self.word >> 56
            self.word = (self.word << 8) & MASK
            self.left -= 1
            self.consumed += 1
        return bytes(result)
