"""
sp6 merge
test bin result:
ff ff 00 00 ff ff ff ff
ff ff ff ff ff ff ff ff
ff ff ff ff ff ff ff ff
ff ff ff ff ff ff ff ff
F4 B9 55 56 7F 29 CF E0
DA 50 03 0E 6E 37 EA 60
9B 8E EB 35 85 17 0C E0
BF 26 BC DE 82 88 EF 20
"""
import os
import configparser
import ctypes
import traceback

CONFIG_FILE = r'./merge.ini'

class ConfigClass():
    """merge config"""
    def __init__(self):
        self.config = configparser.ConfigParser()
        if not os.path.isfile(CONFIG_FILE):
            print('config file not found, create new.')
            with open(CONFIG_FILE, 'w') as _: pass
        self.config['outfile'] = {}
        self.config['file1'] = {}
        self.config['file2'] = {}
        self.config['file3'] = {}
        self.config['file4'] = {}
        self.config.read(CONFIG_FILE)

        if not self.config.has_option('outfile', 'path'):
            self.config['outfile']['path'] = './out.bin'

        if not self.config.has_option('file1', 'path'):
            self.config['file1']['path'] = './uboot_spl.bin'
        if not self.config.has_option('file1', 'offset'):
            self.config['file1']['offset'] = '80'
        if not self.config.has_option('file1', 'maxlen'):
            self.config['file1']['end_offset'] = '128K'

        if not self.config.has_option('file2', 'path'):
            self.config['file2']['path'] = './uboot.bin'
        if not self.config.has_option('file2', 'offset'):
            self.config['file2']['offset'] = '128K'
        if not self.config.has_option('file2', 'maxlen'):
            self.config['file2']['end_offset'] = '1M'

        if not self.config.has_option('file3', 'path'):
            self.config['file3']['path'] = './kernel'
        if not self.config.has_option('file3', 'offset'):
            self.config['file3']['offset'] = '1M'
        if not self.config.has_option('file3', 'maxlen'):
            self.config['file3']['end_offset'] = '3M'

        if not self.config.has_option('file4', 'path'):
            self.config['file4']['path'] = './cramfs'
        if not self.config.has_option('file4', 'offset'):
            self.config['file4']['offset'] = '3M'
        if not self.config.has_option('file4', 'maxlen'):
            self.config['file4']['end_offset'] = '10M'

        with open(CONFIG_FILE, 'w') as configfile:
            self.config.write(configfile)
        self.chk_config()

    def chk_config(self):
        """chk config"""
        if self.get_file_offset(1) < 80:
            raise Exception('file1 offset:{offset} < 80.\n'\
                            .format(offset=self.get_file_offset(1)))

    def get_outfile_path(self):
        """get_outfile_path"""
        path = self.config['outfile']['path'].replace(' ', '').strip()
        return os.path.join(path)

    def get_file_path(self, file_no):
        """get_file_path"""
        path = self.config['file%d'%file_no]['path'].replace(' ', '').strip()
        return path

    def __get_file_offset(self, file_no, offset_type):
        """__get_file_offset"""
        offset_str = self.config['file%d'%file_no][offset_type].replace(' ', '').strip()
        if offset_str[-1] in ['b', 'B']:
            return int(offset_str[:-1])
        if offset_str[-1] in ['k', 'K']:
            return int(offset_str[:-1]) * 1024
        if offset_str[-1] in ['m', 'M']:
            return int(offset_str[:-1]) * 1024 * 1024
        if offset_str[-1] in ['g', 'G']:
            return int(offset_str[:-1]) * 1024 * 1024 * 1024
        return int(offset_str)

    def get_file_offset(self, file_no):
        """get_file_offset"""
        return self.__get_file_offset(file_no, 'offset')

    def get_file_end_offset(self, file_no):
        """get_file_end_offset"""
        return self.__get_file_offset(file_no, 'end_offset')

CONFIG = ConfigClass()


class EccClass():
    """get ecc"""
    def __init__(self):
        self.dll = ctypes.CDLL(r'./nucbch.dll')

    def get_ecc(self, bytestring_512):
        """get ecc"""
        if len(bytestring_512) < 512:
            bytestring_512 += b'\xff'*512
            bytestring_512 = bytestring_512[:2048]
        ecc_obj = self.dll.get_ecc(4, ctypes.create_string_buffer(bytestring_512))
        ret = ctypes.string_at(ecc_obj, 8)
        return ret

    def get_page(self, bytestring_2048):
        """get page"""
        if len(bytestring_2048) < 2048:
            bytestring_2048 += b'\xff'*2048
            bytestring_2048 = bytestring_2048[:2048]

        ecc_section = b'\xff\xff\x00\x00' + b'\xff'*28
        for cnt in range(4):
            ecc_obj = self.dll.get_ecc(4, ctypes.create_string_buffer(bytestring_2048[cnt:(cnt+1)*512]))
            ecc_section += ctypes.string_at(ecc_obj, 8)
        return bytestring_2048 + ecc_section


def merge_file(file_no, outfile_handle):
    """merge file"""
    ecc = EccClass()

    file_path = CONFIG.get_file_path(file_no)
    file_offset = CONFIG.get_file_offset(file_no)
    file_end_offset = CONFIG.get_file_end_offset(file_no)
    print('file{no}: {path}, offset: {offset}, end: {end}'\
            .format(no=file_no, path=file_path, offset=file_offset, end=file_end_offset))
    if not file_path or not os.path.isfile(file_path):
        raise Exception('file{no} not exist, merge abort.'.format(no=file_no))
    outfile_handle.seek(file_offset)
    with open(file_path, 'rb') as in_file:
        write_byte = 0
        page_content = in_file.read(2048)
        while page_content:
            page_to_write = ecc.get_page(page_content)
            write_byte += len(page_to_write)
            if write_byte > file_end_offset - file_offset:
                raise Exception('file{no} write overflow.'.format(no=file_no))
            outfile_handle.write(page_to_write)
            page_content = in_file.read(2048)
        for _ in range(write_byte, file_end_offset - file_offset):
            outfile_handle.write(b'\xff')

def fill_head(outfile_handle):
    """file head"""
    outfile_handle.seek(0)

    boot_code_marker = b'\x20TVN'
    outfile_handle.write(boot_code_marker)

    execute_address = b'\x00'*4 # todo
    outfile_handle.write(execute_address)

    image_size = b'\x00'*4 # todo
    outfile_handle.write(image_size)

    decrypt_address = b'\xff'*4
    outfile_handle.write(decrypt_address)

    ddr_initial_marker = b'\x55\xaa\x55\xaa'
    outfile_handle.write(ddr_initial_marker)

    ddr_counter = b'\x00'*4 # todo
    outfile_handle.write(ddr_counter)

def main():
    """main"""
    outfile_path = CONFIG.get_outfile_path()
    print('out file:', outfile_path)

    outfile = open(outfile_path, 'wb')
    fill_head(outfile)
    for cnt in range(1, 5):
        merge_file(cnt, outfile)
    outfile.close()
    print('success')


def del_outfile():
    """delete outfile"""
    try:
        outfile_path = CONFIG.get_outfile_path()
        if os.path.isfile(outfile_path):
            os.remove(outfile_path)
    except Exception:
        print('outfile del failed.')

if __name__ == '__main__':
    try:
        main()
    except Exception:
        traceback.print_exc()
        print('FAILED')
        del_outfile()
        os.system('pause')
