# -*- coding: utf-8 -*-
"""
B站 扫码登录工具
================
解决 Cookie 过期问题：一次性扫码登录，保存 cookie + refresh_token，
之后由 bili_proxy.py 自动续期，无需再手动更新 Cookie。

用法：
    python bili_login.py qr     生成二维码图片（用手机 B站 APP 扫码）
    python bili_login.py poll   查询扫码结果，成功后写入配置
"""
import sys
import os
import json
import time
import urllib.request
import urllib.parse

CFG = r'D:/Program Files/DAUM/PotPlayer/Extension/Media/PlayParse/Bilibili_Config.json'
STATE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bili_auth.json')
QR_PNG = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bili_qr.png')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
GEN = 'https://passport.bilibili.com/x/passport-login/web/qrcode/generate'
POLL = 'https://passport.bilibili.com/x/passport-login/web/qrcode/poll'
REFRESH = 'https://passport.bilibili.com/x/passport-login/web/cookie/info'
RENEW = 'https://passport.bilibili.com/x/passport-login/web/cookie/refresh'


def http_get(url, with_cookies=False):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Referer': 'https://www.bilibili.com',
    })
    resp = urllib.request.urlopen(req, timeout=20)
    body = resp.read().decode('utf-8')
    j = json.loads(body)
    if with_cookies:
        sc = resp.headers.get_all('Set-Cookie') or []
        return j, sc
    return j, None


def parse_set_cookie(sc_list):
    """从 Set-Cookie 列表提取 cookie 字段"""
    jar = {}
    for line in sc_list:
        kv = line.split(';', 1)[0]
        if '=' in kv:
            k, v = kv.split('=', 1)
            jar[k.strip()] = v.strip()
    return jar


def cmd_qr():
    j, _ = http_get(GEN)
    if j.get('code') != 0:
        print('生成二维码失败:', j)
        return 1
    url = j['data']['url']
    key = j['data']['qrcode_key']
    # 保存 key 供 poll 阶段使用
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump({'qrcode_key': key, 'url': url}, f, ensure_ascii=False)
    # 生成二维码图片
    import qrcode
    img = qrcode.make(url)
    img.save(QR_PNG)
    print('二维码已生成:', QR_PNG)
    print('qrcode_key:', key)
    print()
    print('请用手机 B站 APP 扫码登录（APP 左上角扫一扫），')
    print('扫完在 APP 里确认登录，然后执行: python bili_login.py poll')
    return 0


def cmd_poll():
    if not os.path.exists(STATE):
        print('未找到登录状态，请先执行: python bili_login.py qr')
        return 1
    st = json.load(open(STATE, encoding='utf-8'))
    key = st.get('qrcode_key')
    if not key:
        print('状态文件损坏，请重新生成二维码')
        return 1

    url = POLL + '?' + urllib.parse.urlencode({'qrcode_key': key})
    j, sc_list = http_get(url, with_cookies=True)
    if j.get('code') != 0:
        print('查询失败:', j)
        return 1
    d = j.get('data') or {}
    code = d.get('code')
    msg_map = {0: '登录成功', 86101: '未扫码', 86090: '已扫码，等待确认', 86038: '二维码已过期'}
    print('状态:', msg_map.get(code, code))

    if code == 86038:
        print('二维码过期，请重新执行: python bili_login.py qr')
        return 1
    if code != 0:
        print('请在手机上完成扫码确认后重试')
        return 1

    # 成功
    cookies = parse_set_cookie(sc_list or [])
    refresh_token = d.get('refresh_token', '')
    needed = ['SESSDATA', 'bili_jct', 'DedeUserID']
    missing = [k for k in needed if k not in cookies]
    if missing:
        print('响应缺少字段:', missing)
        print('原始 Set-Cookie 数量:', len(sc_list or []))
        return 1

    cookie_str = '; '.join('%s=%s' % (k, v) for k, v in cookies.items())
    print()
    print('拿到 cookie 字段:', ', '.join(cookies.keys()))
    print('refresh_token 长度:', len(refresh_token))

    # 先保存凭证（用户目录，保证可写，即使后面写配置失败也不丢失）
    auth = {
        'refresh_token': refresh_token,
        'cookie': cookie_str,
        'cookies': cookies,
        'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    with open(STATE, 'w', encoding='utf-8') as f:
        json.dump(auth, f, ensure_ascii=False, indent=2)
    print('凭证已保存:', STATE)

    # 再尝试写入配置（Program Files 可能无权限，失败不影响凭证）
    try:
        import re
        raw = open(CFG, 'rb').read().decode('utf-8')
        newraw = re.sub(r'("cookie"\s*:\s*")[^"]*(")',
                        lambda m: m.group(1) + cookie_str.replace('\\', '\\\\').replace('"', '\\"') + m.group(2),
                        raw, count=1)
        bak = CFG + '.bak-' + time.strftime('%Y%m%d')
        if not os.path.exists(bak):
            open(bak, 'wb').write(raw.encode('utf-8'))
            print('原配置已备份:', bak)
        open(CFG, 'wb').write(newraw.encode('utf-8'))
        print('配置已更新 ✓')
    except PermissionError:
        print('配置无写权限（Program Files）——凭证已保存，稍后用 bat 写入')
    except Exception as e:
        print('写配置失败:', e)
    print()
    print('完成。以后 Cookie 过期会自动续期，无需再手动操作。')
    return 0


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    cmd = sys.argv[1].lower()
    if cmd == 'qr':
        return cmd_qr()
    if cmd == 'poll':
        return cmd_poll()
    print('未知命令:', cmd)
    print(__doc__)
    return 1


if __name__ == '__main__':
    sys.exit(main())
