"""
sp6 merge
"""
import os
import sys
import getopt
import configparser
import ctypes
import traceback
import time
import zlib

VERSION = 'V0.3'
DATE = '20181016'

WORKING_PATH = None
SOFTWARE_PATH = os.path.join(os.path.split(os.path.abspath(sys.argv[0]))[0])
SOFTWARE_REAL_PATH = sys._MEIPASS if getattr(sys, 'frozen', False) else SOFTWARE_PATH

SPL_INI_FILE_PATH_DEFAULT = os.path.join(SOFTWARE_REAL_PATH, 'NUC972DF62Y.ini')
NUCBCH_DLL_PATH_DEFAULT = os.path.join(SOFTWARE_REAL_PATH, 'nucbch.dll')
CONFIG_FILE = os.path.join(SOFTWARE_PATH, r'burn.ini')
CONFIG_FILE_CONTENT_DEFAULT = \
r'''# SP6 Burn Files Merge

[outfile]
# ECC位数，支持4或8
ecc_bit = 4

# 烧片文件
burn_file_name = flash.bin
burn_file_path = .

# NuWriter烧写文件
pack_file_name = pack.bin
pack_file_path = .

# 输入文件
# type: data/uboot/env, uboot文件可用spl_ini_path项自定义spl头配置文件
# offset:偏移位置，支持单位B/K/M/G，不带单位默认B
[file1]
type = uboot
path = u-boot-spl.bin
offset = 0
spl_ini_path = 

[file2]
type = data
path = u-boot.bin
offset = 128K

[file3]
type = data
path = uImage
offset = 768K

[file4]
type = data
path = cramfs.img
offset = 3M
'''
class ConfigClass():
    """merge config"""
    def __init__(self):
        if not os.path.isfile(CONFIG_FILE):
            print('config file not found, create new.')
            with open(CONFIG_FILE, 'w', encoding='utf-8') as new_file:
                new_file.write(CONFIG_FILE_CONTENT_DEFAULT)
        self.config = configparser.ConfigParser()
        self.config.read(CONFIG_FILE, encoding='utf-8-sig')

    def chk_config(self):   #todo: 检查文件偏移是否合法，是否会覆盖
        """chk config"""
        if not self.config.has_section('outfile')\
            or not self.config.has_section('file1'):
            raise Exception('config file err, please delete it and try again.')
        ecc_bit = self.config['outfile']['ecc_bit']
        if not (ecc_bit.isdigit() and int(ecc_bit) in [4, 8]):
            raise Exception('ecc bit[%s] invalid.'%self.config['outfile']['ecc_bit'])

    def outfile_cfg(self, key):
        """get outfile cfg"""
        return self.config['outfile'].get(key, '')

    def infile_cfg(self, file_no, key):
        """get infile cfg"""
        section = 'file' + str(file_no)
        if self.config.has_section(section):
            return self.config[section].get(key, '')
        else:
            return None

CONFIG = ConfigClass()


class EccClass():
    """get ecc"""
    def __init__(self):
        self.dll = ctypes.CDLL(NUCBCH_DLL_PATH_DEFAULT)
        self.ecc_bit = int(CONFIG.outfile_cfg('ecc_bit'))
        if self.ecc_bit not in [4, 8]:
            raise Exception('ecc bit[%d] invalid.'%self.ecc_bit)
        # print('ecc type: %dbit'%self.ecc_bit)

    def get_page(self, bytestring_2048):
        """get page"""
        if len(bytestring_2048) < 2048:
            bytestring_2048 += b'\xff'*2048
            bytestring_2048 = bytestring_2048[:2048]

        ecc_section = (b'\xff\xff\x00\x00' + b'\xff'*28) if self.ecc_bit == 4 else (b'\xff\xff\x00\x00' + b'\xff'*64)
        for cnt in range(4):
            bytestring = bytestring_2048[cnt*512:(cnt+1)*512]
            ecc_obj = self.dll.get_ecc(self.ecc_bit, 1 if cnt == 0 else 0, ctypes.create_string_buffer(bytestring))
            ecc_section += ctypes.string_at(ecc_obj, 8 if self.ecc_bit == 4 else 15)
        return bytestring_2048 + ecc_section

def get_spl_head(spl_file_path, spl_ini_file_path):
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
    if not spl_ini_file_path:
        print('use default spl ini file')
        spl_ini_file_path = SPL_INI_FILE_PATH_DEFAULT
    else:
        print('spl ini file:', spl_ini_file_path)
    with open(spl_ini_file_path, 'r') as spl_ini_file:
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
    spl_head = boot_code_marker + execute_address + image_size + decrypt_address\
            + ddr_initial_marker + ddr_counter + ddr_content
    return spl_head


def get_offset(offset_str):
    """get_offset"""
    offset_str = offset_str.replace(' ', '').strip()
    if offset_str[-1] in ['b', 'B']:
        return int(offset_str[:-1])
    if offset_str[-1] in ['k', 'K']:
        return int(offset_str[:-1]) * 1024
    if offset_str[-1] in ['m', 'M']:
        return int(offset_str[:-1]) * 1024 * 1024
    if offset_str[-1] in ['g', 'G']:
        return int(offset_str[:-1]) * 1024 * 1024 * 1024
    return int(offset_str)


def get_w_content(infile_no, infile_type):
    """get env file content"""
    infile_path = CONFIG.infile_cfg(infile_no, 'path')
    if infile_type == 'env':
        with open(infile_path, 'rb') as in_file:
            w_content = in_file.read().replace(b'\x0d\x0a', b'\x00')
        if len(w_content) < 64 * 1024 - 4:
            w_content += b'\x00'*(64*1024 - 4 - len(w_content))
        w_content = zlib.crc32(w_content).to_bytes(4, 'little') + w_content
    elif infile_type == 'uboot':
        spl_head = get_spl_head(infile_path, CONFIG.infile_cfg(infile_no, 'spl_ini_path'))
        in_file = open(infile_path, 'rb')
        w_content = spl_head + in_file.read()
        in_file.close()
    elif infile_type == 'data':
        in_file = open(infile_path, 'rb')
        w_content = in_file.read()
        in_file.close()
    else:
        raise Exception('file[{no}] type {type} invalid, merge abort.'\
            .format(no=infile_no, type=infile_type))
    return w_content


def merge_burn_file(infile_no, w_to_file_h):
    """merge file"""
    ecc = EccClass()

    infile_path = CONFIG.infile_cfg(infile_no, 'path')
    infile_offset = get_offset(CONFIG.infile_cfg(infile_no, 'offset'))
    if ecc.ecc_bit == 4:
        infile_offset += infile_offset // 2048 * 64
    elif ecc.ecc_bit == 8:
        infile_offset += infile_offset // 2048 * 128
    else:
        raise Exception('ecc bit {bit} invalied.'.format(bit=ecc.ecc_bit))
    infile_type = CONFIG.infile_cfg(infile_no, 'type').lower().strip()
    print('burn:infile{no}({path}), type: {type}, offset: {offset}'\
            .format(no=infile_no, path=infile_path, type=infile_type, offset=infile_offset))
    if not infile_path or not os.path.isfile(infile_path):
        raise Exception('file{no} not exist, merge abort.'.format(no=infile_no))

    w_file_pos = w_to_file_h.tell()
    for _ in range(w_file_pos, infile_offset):
        w_to_file_h.write(b'\xff')
    print('fill ', w_file_pos, '~', infile_offset)

    w_content = get_w_content(infile_no, infile_type)
    for cnt in range(0, len(w_content), 2048):
        page_content = w_content[cnt: cnt + 2048]
        page_to_write = ecc.get_page(page_content)
        w_to_file_h.write(page_to_write)


def merge_pack_file(infile_no, w_to_file_h):
    """merge pack file"""
    infile_path = CONFIG.infile_cfg(infile_no, 'path')
    infile_offset = get_offset(CONFIG.infile_cfg(infile_no, 'offset'))
    infile_type = CONFIG.infile_cfg(infile_no, 'type').lower().strip()
    print('pack:infile{no}({path}), type: {type}, offset: {offset}'\
            .format(no=infile_no, path=infile_path, type=infile_type, offset=infile_offset))
    if not infile_path or not os.path.isfile(infile_path):
        raise Exception('file{no} not exist, merge abort.'.format(no=infile_no))

    infile_type_no = {'data': 0, 'env': 1, 'uboot': 2}.get(infile_type)
    w_content = get_w_content(infile_no, infile_type)
    infile_len = len(w_content)
    w_to_file_h.write(infile_len.to_bytes(4, 'little'))
    w_to_file_h.write(infile_offset.to_bytes(4, 'little'))
    w_to_file_h.write(infile_type_no.to_bytes(4, 'little'))
    w_to_file_h.write(b'\xff'*4)
    w_to_file_h.write(w_content)


def start_create(out_path=''):
    """main"""
    try:
        out_burn_file_path = os.path.join(\
            out_path if out_path else CONFIG.outfile_cfg('burn_file_path'),\
            CONFIG.outfile_cfg('burn_file_name'))
        out_pack_file_path = os.path.join(\
            out_path if out_path else CONFIG.outfile_cfg('pack_file_path'),\
            CONFIG.outfile_cfg('pack_file_name'))
        print('ECC {bit}bit'.format(bit=CONFIG.outfile_cfg('ecc_bit')))
        print('out burn file:', out_burn_file_path)
        print('out pack file:', out_pack_file_path)
        burnfile = open(out_burn_file_path, 'wb') if out_burn_file_path else None
        packfile = open(out_pack_file_path, 'wb') if out_pack_file_path else None
        if packfile:
            infile_num = 0
            infile_size_sum = 0
            for cnt in range(1, 10):
                if not CONFIG.infile_cfg(cnt, 'path'):
                    break
                infile_num += 1
                infile_size_sum += (os.path.getsize(CONFIG.infile_cfg(cnt, 'path')) + 64*1024 - 1)\
                                    // (64*1024) * (64*1024) # 64k对齐
            pack_action = 5
            packfile.write(pack_action.to_bytes(4, 'little'))
            packfile.write(infile_size_sum.to_bytes(4, 'little'))
            packfile.write(infile_num.to_bytes(4, 'little'))
            packfile.write(b'\xff'*4)
        for cnt in range(1, 10):
            if not CONFIG.infile_cfg(cnt, 'path'):
                break
            if burnfile: merge_burn_file(cnt, burnfile)
            if packfile: merge_pack_file(cnt, packfile)
        return 0
    except Exception:
        traceback.print_exc()
        return -1
    finally:
        if burnfile: burnfile.close()
        if packfile: packfile.close()


def del_outfile(out_path=''):
    """delete outfile"""
    try:
        out_burn_file_path = os.path.join(\
            out_path if out_path else CONFIG.outfile_cfg('burn_file_path'),\
            CONFIG.outfile_cfg('burn_file_name'))
        out_pack_file_path = os.path.join(\
            out_path if out_path else CONFIG.outfile_cfg('pack_file_path'),\
            CONFIG.outfile_cfg('pack_file_name'))
        if os.path.isfile(out_burn_file_path):
            os.remove(out_burn_file_path)
        if os.path.isfile(out_pack_file_path):
            os.remove(out_pack_file_path)
    except Exception:
        traceback.print_exc()
        print('outfile del failed.')


if __name__ == '__main__':
    out_file_path = None
    opts, args = getopt.gnu_getopt(sys.argv[1:], "o:")
    if not args:
        WORKING_PATH = SOFTWARE_PATH
    else:
        WORKING_PATH = args[0]
    for op, value in opts:
        if op == '-o':
            out_file_path = os.path.abspath(value)
    try:
        CONFIG.chk_config()
        if not os.path.isdir(WORKING_PATH):
            raise Exception('ERROR: working path{path} invalid.'.format(path=WORKING_PATH))
        if out_file_path and not os.path.isdir(out_file_path):
            os.makedirs(out_file_path)

        tm_start = time.time()
        print('SP6 Burn File Creator {ver}({date}).Designed by Kay.'.format(ver=VERSION, date=DATE))
        print('WORKING_PATH:', WORKING_PATH)
        print('CONFIG_FILE:', CONFIG_FILE)
        os.chdir(WORKING_PATH)
        if start_create(out_file_path) == 0:
            print('success')
        else:
            raise Exception('!!FAILED!!')
        print('time use {tm:.1f}s'.format(tm=time.time() - tm_start))
        sys.exit(0)
    except Exception:
        traceback.print_exc()
        os.system('color 47')
        del_outfile(out_file_path)
        time.sleep(3)
        os.system('color 07')
        sys.exit(1)
