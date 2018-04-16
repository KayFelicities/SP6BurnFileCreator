"""
sp6 merge
"""
import os
import configparser
import ctypes
import traceback
import time

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

        if not self.config.has_option('outfile', 'merge_file_path'):
            self.config['outfile']['merge_file_path'] = ''
        if not self.config.has_option('outfile', 'file1'):
            self.config['outfile']['file1'] = './out_u-boot-spl.bin'
        if not self.config.has_option('outfile', 'file2'):
            self.config['outfile']['file2'] = './out_u-boot.bin'
        if not self.config.has_option('outfile', 'file3'):
            self.config['outfile']['file3'] = './out_uImage.bin'
        if not self.config.has_option('outfile', 'file4'):
            self.config['outfile']['file4'] = './out_cramfs.bin'

        if not self.config.has_option('file1', 'path'):
            self.config['file1']['path'] = './u-boot-spl.bin'
        if not self.config.has_option('file1', 'offset'):
            self.config['file1']['offset'] = '0'
        if not self.config.has_option('file1', 'maxlen'):
            self.config['file1']['end_offset'] = '128K'
        if not self.config.has_option('file1', 'head_ini_path'):
            self.config['file1']['head_ini_path'] = './NUC972DF62Y.ini'

        if not self.config.has_option('file2', 'path'):
            self.config['file2']['path'] = './u-boot.bin'
        if not self.config.has_option('file2', 'offset'):
            self.config['file2']['offset'] = '128K'
        if not self.config.has_option('file2', 'maxlen'):
            self.config['file2']['end_offset'] = '1M'

        if not self.config.has_option('file3', 'path'):
            self.config['file3']['path'] = './uImage'
        if not self.config.has_option('file3', 'offset'):
            self.config['file3']['offset'] = '1M'
        if not self.config.has_option('file3', 'maxlen'):
            self.config['file3']['end_offset'] = '3M'

        if not self.config.has_option('file4', 'path'):
            self.config['file4']['path'] = './cramfs.img'
        if not self.config.has_option('file4', 'offset'):
            self.config['file4']['offset'] = '3M'
        if not self.config.has_option('file4', 'maxlen'):
            self.config['file4']['end_offset'] = '10M'

        with open(CONFIG_FILE, 'w') as configfile:
            self.config.write(configfile)
        self.chk_config()

    def chk_config(self):
        """chk config"""
        pass

    def get_out_merge_file_path(self):
        """get_out_merge_file_path"""
        path = self.config['outfile']['merge_file_path'].replace(' ', '').strip()
        return os.path.join(path)

    def get_out_file_path(self, file_no):
        """get_out_file_path"""
        path = self.config['outfile']['file%d'%file_no].replace(' ', '').strip()
        return os.path.join(path)

    def get_spl_ini_path(self):
        """get_spl_ini_path"""
        path = self.config['file1']['head_ini_path'].replace(' ', '').strip()
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

    def get_page(self, bytestring_2048):
        """get page"""
        if len(bytestring_2048) < 2048:
            bytestring_2048 += b'\xff'*2048
            bytestring_2048 = bytestring_2048[:2048]

        ecc_section = b'\xff\xff\x00\x00' + b'\xff'*28
        for cnt in range(4):
            bytestring = bytestring_2048[cnt*512:(cnt+1)*512]
            with open(r'./debug.log', 'ab+') as debug_file:
                debug_file.write(bytestring)
            ecc_obj = self.dll.get_ecc(4, 1 if cnt == 0 else 0, ctypes.create_string_buffer(bytestring))
            ecc_section += ctypes.string_at(ecc_obj, 8)
        return bytestring_2048 + ecc_section

def get_spl_head(spl_file_path):
    """file head"""
    boot_code_marker = b'\x20TVN'
    execute_address = 0x200.to_bytes(4, 'little') # 固定0x200
    spl_size = os.path.getsize(spl_file_path)
    print('spl size: ', spl_size)
    image_size = spl_size.to_bytes(4, 'little')
    decrypt_address = b'\xff'*4
    ddr_initial_marker = b'\x55\xaa\x55\xaa'

    counter = 0
    ddr_content = b''
    with open(CONFIG.get_spl_ini_path(), 'r') as spl_ini_file:
        while True:
            line = spl_ini_file.readline()
            if not line:
                break
            ddr = line.split('=')
            if len(ddr) != 2:
                continue
            ddr_content += int(ddr[0], 0).to_bytes(4, 'little')
            ddr_content += int(ddr[1], 0).to_bytes(4, 'little')
            counter += 1
        dummy_num = 4 - ((counter+1) % 4)
        for _ in range(dummy_num):
            ddr_content += b'\x00'*8
    ddr_counter = counter.to_bytes(4, 'little')

    ret = boot_code_marker + execute_address + image_size + decrypt_address\
            + ddr_initial_marker + ddr_counter + ddr_content
    return ret

def merge_file(file_no, merge_file_handle):
    """merge file"""
    ecc = EccClass()

    file_path = CONFIG.get_file_path(file_no)
    file_offset = CONFIG.get_file_offset(file_no)
    file_end_offset = CONFIG.get_file_end_offset(file_no)
    file_out_path = CONFIG.get_out_file_path(file_no)
    out_file = open(file_out_path, 'wb') if file_out_path else None
    print('file{no}: {path}, offset: {offset}, end: {end}, out file: {out}'\
            .format(no=file_no, path=file_path, offset=file_offset, end=file_end_offset, out=file_out_path))
    if not file_path or not os.path.isfile(file_path):
        raise Exception('file{no} not exist, merge abort.'.format(no=file_no))
    if merge_file_handle: merge_file_handle.seek(file_offset)

    with open(file_path, 'rb') as in_file:
        write_byte = 0
        if file_no == 1:
            spl_head = get_spl_head(file_path)
            page_content = spl_head + in_file.read(2048 - len(spl_head))
        else:
            page_content = in_file.read(2048)
        while page_content:
            page_to_write = ecc.get_page(page_content)
            write_byte += len(page_to_write)
            if write_byte > file_end_offset - file_offset:
                raise Exception('file{no} write overflow.'.format(no=file_no))
            if out_file: out_file.write(page_to_write)
            if merge_file_handle: merge_file_handle.write(page_to_write)
            page_content = in_file.read(2048)
        for _ in range(write_byte, file_end_offset - file_offset):
            if merge_file_handle: merge_file_handle.write(b'\xff')
    if out_file: out_file.close()

def main():
    """main"""
    out_merge_file_path = CONFIG.get_out_merge_file_path()
    print('out merge file:', out_merge_file_path)

    outfile = open(out_merge_file_path, 'wb') if out_merge_file_path else None
    for cnt in range(1, 5):
        merge_file(cnt, outfile)
    if outfile: outfile.close()
    print('success')


def del_outfile():
    """delete outfile"""
    try:
        outfile_path = CONFIG.get_out_merge_file_path()
        if os.path.isfile(outfile_path):
            os.remove(outfile_path)
        for cnt in range(1, 5):
            outfile_path = CONFIG.get_out_file_path(cnt)
            if os.path.isfile(outfile_path):
                os.remove(outfile_path)
    except Exception:
        print('outfile del failed.')

if __name__ == '__main__':
    tm_start = time.time()
    try:
        main()
    except Exception:
        traceback.print_exc()
        print('FAILED')
        del_outfile()
    finally:
        print('time use {tm:.1f}s'.format(tm=time.time() - tm_start))
        os.system('pause')
