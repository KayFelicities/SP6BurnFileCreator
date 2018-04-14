"""
sp6 merge
test bin result:
ff ff 00 00 ff ff ff ff
ff ff ff ff ff ff ff ff
ff ff ff ff ff ff ff ff
ff ff ff ff ff ff ff ff
f4 b9 55 56 7f 29 cf e0
22 79 f1 4b b8 0d c0 20
63 a7 19 70 53 2d 26 a0
47 0f 4e 9b 54 b2 c5 60
"""
import ctypes


class EccClass():
    """get ecc"""
    def __init__(self):
        self.dll = ctypes.CDLL(r'./nucbch.dll')

    def get_ecc(self, bytestring_512):
        """get ecc"""
        if len(bytestring_512) < 512:
            bytestring_512 += '/xff'*512
        ecc_obj = self.dll.get_ecc(4, ctypes.create_string_buffer(bytestring_512[:512]))
        ret = ctypes.string_at(ecc_obj, 8)
        return ret

def main():
    """main"""
    ecc = EccClass()
    with open(r'./test_bin.bin', 'rb') as file:
        b512 = file.read(512)
        print(ecc.get_ecc(b512))


if __name__ == '__main__':
    main()
