# -*- coding: utf-8 -*-
"""
B站 Cookie 自动续期模块
========================
SESSDATA 过期后无法续期，必须在过期前用 refresh_token 换新。
策略：服务启动后检查一次，距上次刷新超过 7 天则自动刷新。

刷新成功后写回 bili_auth.json（用户目录，无需提权）。
配置文件 Bilibili_Config.json 在 Program Files 无法直接写，
由插件优先读取 bili_auth.json 中的 cookie 来覆盖。
"""
import os
import json
import time
import urllib.request
import urllib.parse

AUTH_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bili_auth.json')
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'bili_refresh_state.json')

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36')
INFO_URL = 'https://passport.bilibili.com/x/passport-login/web/cookie/info'
REFRESH_URL = 'https://passport.bilibili.com/x/passport-login/web/cookie/refresh'

REFRESH_INTERVAL_DAYS = 7   # 每 7 天刷新一次（SESSDATA 有效期约 30 天，留足余量）


def _log(msg):
    try:
        print(time.strftime("[%H:%M:%S] ") + str(msg), flush=True)
    except Exception:
        pass


def _load_auth():
    if not os.path.exists(AUTH_FILE):
        return None
    try:
        return json.load(open(AUTH_FILE, encoding='utf-8'))
    except Exception:
        return None


def _save_auth(auth):
    with open(AUTH_FILE, 'w', encoding='utf-8') as f:
        json.dump(auth, f, ensure_ascii=False, indent=2)


def _need_refresh():
    """距上次刷新超过 N 天才刷新"""
    try:
        st = json.load(open(STATE_FILE, encoding='utf-8'))
        last = st.get('last_refresh_ts', 0)
    except Exception:
        last = 0
    return (time.time() - last) > REFRESH_INTERVAL_DAYS * 86400


def _mark_refreshed(ok):
    st = {'last_refresh_ts': time.time(), 'last_ok': ok}
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(st, f, ensure_ascii=False)
    except Exception:
        pass


def refresh_cookie():
    """尝试刷新 Cookie。成功返回新的 cookie 字符串，失败返回 None"""
    auth = _load_auth()
    if not auth:
        _log("cookie-refresh: no auth file, skip")
        return None
    cookie = auth.get('cookie', '')
    refresh_token = auth.get('refresh_token', '')
    if not cookie or not refresh_token:
        _log("cookie-refresh: missing cookie/refresh_token, skip")
        return None

    cookies = auth.get('cookies') or {}
    if not cookies:
        # 从 cookie 字符串解析
        for part in cookie.split(';'):
            part = part.strip()
            if '=' in part:
                k, v = part.split('=', 1)
                cookies[k.strip()] = v.strip()
    csrf = cookies.get('bili_jct', '')

    try:
        # 1) 换取 refresh_csrf
        u = INFO_URL + '?' + urllib.parse.urlencode({'csrf': csrf})
        req = urllib.request.Request(u, headers={
            'User-Agent': UA,
            'Referer': 'https://www.bilibili.com',
            'Cookie': cookie,
        })
        resp = urllib.request.urlopen(req, timeout=20)
        j = json.loads(resp.read().decode('utf-8'))
        if j.get('code') != 0:
            _log("cookie-refresh: info failed code=%s" % j.get('code'))
            _mark_refreshed(False)
            return None
        refresh_csrf = (j.get('data') or {}).get('refresh_csrf', '')

        # 2) 刷新
        data = urllib.parse.urlencode({
            'csrf': csrf,
            'refresh_csrf': refresh_csrf,
            'refresh_token': refresh_token,
        }).encode('utf-8')
        req = urllib.request.Request(REFRESH_URL, data=data, headers={
            'User-Agent': UA,
            'Referer': 'https://www.bilibili.com',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Cookie': cookie,
        })
        resp = urllib.request.urlopen(req, timeout=20)
        j = json.loads(resp.read().decode('utf-8'))
        sc = resp.headers.get_all('Set-Cookie') or []
        if j.get('code') != 0:
            _log("cookie-refresh: refresh failed code=%s" % j.get('code'))
            _mark_refreshed(False)
            return None

        # 3) 解析新 cookie
        new_cookies = dict(cookies)
        for line in sc:
            kv = line.split(';', 1)[0]
            if '=' in kv:
                k, v = kv.split('=', 1)
                new_cookies[k.strip()] = v.strip()
        new_cookie_str = '; '.join('%s=%s' % (k, v) for k, v in new_cookies.items())
        new_refresh = (j.get('data') or {}).get('refresh_token', refresh_token)

        # 4) 保存
        auth.update({
            'cookie': new_cookie_str,
            'cookies': new_cookies,
            'refresh_token': new_refresh,
            'updated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        })
        _save_auth(auth)
        _mark_refreshed(True)
        _log("cookie-refresh: OK, new SESSDATA len=%d" % len(new_cookies.get('SESSDATA', '')))
        return new_cookie_str
    except Exception as e:
        _log("cookie-refresh: error %s" % e)
        _mark_refreshed(False)
        return None


def maybe_refresh():
    """入口：按需刷新（距上次超过 7 天才执行）"""
    if not _need_refresh():
        return
    _log("cookie-refresh: checking...")
    ok = refresh_cookie()
    if ok:
        _log("cookie-refresh: done")
    else:
        _log("cookie-refresh: failed or skipped (may need re-login)")
