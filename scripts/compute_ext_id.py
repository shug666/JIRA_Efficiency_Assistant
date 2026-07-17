#!/usr/bin/env python3
"""根据 manifest.json 的 key 字段计算 Chrome 扩展 ID。

Chrome 扩展 ID = SHA256(public_key_DER)[:16] 每 4bit 映射到 a-p。
key 字段是 base64 编码的 DER 公钥，所以直接 base64 decode 即可。
"""
import base64
import hashlib
import sys


def compute_ext_id(key_b64: str) -> str:
    pubkey_bytes = base64.b64decode(key_b64)
    digest = hashlib.sha256(pubkey_bytes).digest()
    # 取前 16 字节，每字节拆成高低两个 4 bit，映射到 a-p，共 32 字符
    ext_id = ''
    for byte in digest[:16]:
        ext_id += chr(ord('a') + (byte >> 4))
        ext_id += chr(ord('a') + (byte & 0x0F))
    return ext_id


if __name__ == '__main__':
    if len(sys.argv) > 1:
        key_b64 = sys.argv[1]
    else:
        key_b64 = input('粘贴 manifest.json 的 key 字段值: ').strip()
    ext_id = compute_ext_id(key_b64)
    print('扩展 ID:', ext_id)
    print('长度:', len(ext_id))
    # 用于 update.xml 和安装策略
    print()
    print('GitHub Pages update_url 示例:')
    print(f'  https://shug666.github.io/JIRA_Efficiency_Assistant/update.xml')
