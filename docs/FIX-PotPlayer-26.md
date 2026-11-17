# PotPlayer 26.x 兼容性修复说明

> 本文档记录针对 PotPlayer **26.x**（2026 年起的新版本）适配本插件的全部改动。
> 原插件最后更新于 2025-05-22（v1.3），而 PotPlayer 26.x 对 AngelScript 扩展系统做了较大重构，
> 导致原版插件在新版播放器上出现多种播放失败。以下修复已在 PotPlayer **26.10.21** 上实测通过。

---

## 一、问题现象

在原版插件 + PotPlayer 26.x 的组合下，会出现以下一种或多种症状：

| 现象 | 具体表现 |
|---|---|
| 黑屏转圈 | 点击播放后一直加载，无画面无声音 |
| 报错「服务器已关闭或地址错误」 | 弹窗提示，附带「在渲染下列 Pin 时失败了」 |
| 只有第一个分P能播 | 合集列表里第 1 集正常，第 2 集起全部「文件无法播放」 |
| 有画面没声音 | 视频正常渲染，但音轨完全静音 |
| 画质模糊 | 明明选了 1080P，实际画面像 360P |
| 失败无任何提示 | 因为原插件不设置 `errorMessage` 字段 |

---

## 二、根本原因

排查后确认是 **6 个独立问题叠加**，而非单一故障：

### 1. 旧式账号回调被废弃 → 配置文件读不进来

PotPlayer 26.x 的 `Extension/api.txt` 中，`GetUserText` / `GetPasswordText` / `ServerCheck` /
`ServerLogin` 这些旧接口**已全部移除**，改为 WebView2 登录 + `HostGetCookie()`。

而原插件把「读取配置文件」写在 `ServerLogin()` 里，这个方法在新版中**永远不会被调用**，
于是 `ConfigData` 始终是默认值：Cookie 为空、弹幕地址为空。

### 2. `HostSetUrlHeaderHTTP` 写入注册表但不生效

插件通过该 API 给 CDN 域名设置 Referer，注册表 `_UrlHeader` 里确实能看到值，
但 **实际播放时 PotPlayer 并未把 Referer 发出去**。

而 B站 CDN 强制校验 Referer，实测：

```
带 Referer  → HTTP 206  正常返回视频流
不带 Referer → HTTP 403  拒绝访问
```

403 在 PotPlayer 里就表现为「服务器已关闭或地址错误」+「Pin 渲染失败」。

### 3. 弹幕服务器域名已失效

默认配置 `server: https://subtitle.chen310.repl.co` —— 该域名 **DNS 已无法解析**（NXDOMAIN），
Replit 的免费托管服务早已关停。插件会把每集的弹幕当成「字幕」去加载，请求必然失败。

### 4. `durl` 分支会把空 URL 塞进画质列表

原代码遍历 `accept_quality` 为每个画质单独请求播放地址，但请求失败时
`qualityitem["url"]` 保持空字符串，仍然被 `insertLast` 加入 `QualityList`。
PotPlayer 一旦选中这个空项，就是「文件无法播放」。

同时 `int quality_codecid;` 未初始化，失败时 `itag` 会算成错误值。

### 5. DASH 分离流音轨配对失败 → 无声

`fnval=4048` 返回的是 DASH 格式，**视频流和音频流是分离的两个文件**，
需要播放器按 `itag` 自行配对合并。PotPlayer 26.x 下该机制失效，
结果就是画面正常、音轨为空。

### 6. 多P 缺少唯一标识

原插件从不设置 `MetaData["vid"]`，而新版 API 文档明确要求
「Give each part of a multi-part video its own vid」，
否则多P 的播放进度、音轨记忆会相互串扰。

---

## 三、修复清单

修改后的 `MediaPlayParse - Bilibili.as` 相对原版 **+157 行 / -28 行**（1925 → 2054 行），共 11 处改动：

| # | 改动 | 作用 |
|---|---|---|
| 1 | `EnsureConfig()` 懒加载配置 | 在 `PlaylistParse` / `PlayitemParse` 入口读取配置文件，绕过被废弃的 `ServerLogin` |
| 2 | 弹幕/字幕 URL 空值保护 | `danmakuUrl.empty()` 时不再构造无效字幕地址 |
| 3 | `forceMuxed` 开关 + `getFnval()` | 默认走 `fnval=1`（音视频合一的 mp4），彻底解决无声 |
| 4 | durl 循环只保留最高画质 | 不再插入空 URL 项，也不会误选 360P |
| 5 | `quality_codecid` 初始化 | 避免 itag 计算出错值 |
| 6 | `MetaData["vid"] = bvid + "_p" + p` | 每个分P 独立标识，进度/音轨记忆互不干扰 |
| 7 | 4 处 `errorMessage` | 失败时明确告知原因，不再静默 |
| 8 | `post()` 自动降级 | `HostUrlGetStringWithAPI` 返回空时自动改用 `HostUrlGetString` 重试 |
| 9 | `ApplyCdnHeader()` + `WrapProxy()` | 精确到实际 CDN 子域名设置 Referer；并接入本地转发服务 |
| 10 | `proxyRetry` 失败计数 | 服务不可用时最多重试 5 次即停止，避免每个 URL 都等连接超时拖慢解析 |
| 11 | `OnInitialize` / `OnFinalize` 生命周期钩子 | 播放器启动时拉起转发服务、关闭时通知其退出，实现服务生命周期与播放器绑定 |

### 关于第 9 项（最终解法）

前 8 项修复后，解析链路已完全正常（控制台可见 `result: OK`、URL 成功获取），
但 PotPlayer 仍然发不出 Referer，CDN 依旧 403。因此增加**本地转发方案**：

```
PotPlayer ──► http://127.0.0.1:18999/p/<id>
                     │
                     ├─ 本地服务补上 Referer/UA/Origin
                     ▼
              B站 CDN（返回 206 视频流）
                     │
                     ▼
              流式转发回 PotPlayer
```

由于 PotPlayer 请求的是本机地址，不涉及任何 header 校验，问题被彻底绕开。

`proxy/bili_proxy.py` 即该服务，仅依赖 Python 3 标准库，无需安装任何第三方包。
服务未启动时，插件会自动回退到直连 CDN（即修复前的行为），不会导致更差的结果。

### 关于第 11 项（生命周期绑定）

转发服务是常驻进程，但不应长期占用后台。因此把它与 PotPlayer 的生命周期绑定：

```angelscript
// 启动时：探测 → 未运行则拉起
void OnInitialize() {
    ...
    EnsureConfig();
    EnsureProxyStarted();
}

// 关闭时：通知服务退出
void OnFinalize() {
    HostUrlGetString("http://127.0.0.1:18999/shutdown", "", "", "", true);
}
```

`EnsureProxyStarted()` 先请求 `/ping`：

- 已有实例在跑 → 直接复用，不重复启动
- 没有实例 → 通过 `C:\Windows\System32\cmd.exe /c "<launch.bat 路径>"` 启动

> 注意：`HostExecuteProgram` **必须给完整路径**。实测传 `wscript.exe` 这种裸文件名会静默失败，找不到程序。
> 另外 `launch.bat` 里用 `start` 确保非阻塞，否则会卡住 `OnInitialize`。

如果 PotPlayer 异常退出（`OnFinalize` 来不及执行），服务内的看门狗会在约 25 秒后自行退出：

```python
def _watchdog():
    miss = 0
    while not _shutdown_evt.is_set():
        time.sleep(WATCH_INTERVAL)          # 5 秒
        if time.time() - _started_at < WATCH_STARTUP_GRACE:
            continue                        # 启动后 15 秒宽限
        if _potplayer_alive():
            miss = 0
            continue
        miss += 1
        if miss >= WATCH_MISS_LIMIT:        # 连续 2 次未找到
            os._exit(0)
```

> 进程检测用 `tasklist` 全量输出后做 bytes 匹配。中文系统下 `tasklist` 输出 GBK，
> 若用 `text=True` 会触发 UTF-8 解码异常，因此必须按 bytes 处理。

### 关于 HostExecuteProgram 阻塞（播放器未响应）

`HostExecuteProgram` 会捕获子进程的 stdout 并等待管道 EOF。如果被启动的进程
继承了这条管道，调用方就永远等不到 EOF，表现为 PotPlayer 界面「未响应」。

踩过的三种错误写法：

| 写法 | 结果 |
|---|---|
| `start "" pythonw script.py` | 阻塞。子进程继承 bat 的 stdout 管道 |
| `start "" pythonw script.py >nul 2>&1` | 仍阻塞。`start` 的子进程依旧继承句柄 |
| Python 里 `os.dup2(devnull, 1)` | 无效。pythonw 启动到执行 dup2 之前句柄已被持有 |

**正确做法**：让新进程由 Shell 派生，而不是直接继承当前进程。

```bat
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launch.ps1"
```

```powershell
Start-Process -FilePath 'D:\python\pythonw.exe' `
              -ArgumentList 'C:\...ili_proxy.py' `
              -WindowStyle Hidden
```

`Start-Process` 走 Shell 派生，新进程**不会继承**调用者的标准句柄，
因此 `powershell` 执行完立即退出，`HostExecuteProgram` 随之返回。

> 同理，`wscript.exe` 也要给完整路径（`C:\Windows\System32\wscript.exe`）——
> `HostExecuteProgram` 不走 PATH 查找，裸文件名会静默失败。

### 调试方式

正常使用时**不会弹出控制台**（`debug: false`）。需要排查时按需打开：

1. **插件解析日志** —— 把 `Bilibili_Config.json` 里的 `debug` 改为 `true`，重启 PotPlayer。
   播放时会弹出 AngelScript 控制台，输出 `request:` / `result:` / `url:` / `proxy-id:` 等。
2. **错误提示** —— 即便 `debug: false`，解析失败时 PotPlayer 仍会显示
   `errorMessage`（如 `Bilibili: API request failed`）。
3. **转发服务** —— 需要脱离播放器单独调试时运行：
   ```bat
   python proxy\bili_proxy.py --no-watch
   ```
   此时日志直接输出到控制台窗口。

---

## 四、安装步骤

### 1. 复制插件文件

将以下文件复制到 PotPlayer 安装目录：

```
<PotPlayer 安装目录>\Extension\Media\PlayParse\
    ├─ MediaPlayParse - Bilibili.as
    ├─ MediaPlayParse - Bilibili.ico
    └─ Bilibili_Config.json

<PotPlayer 安装目录>\Extension\Media\UrlList\
    ├─ MediaUrlList - Bilibili.as
    └─ MediaUrlList - Bilibili.ico
```

> 若目录已存在同名文件，直接覆盖。建议先备份原文件。

### 2. 填写 Cookie

编辑 `Bilibili_Config.json`，把 `"cookie": ""` 填成你自己的 B站 Cookie。

获取方法见 <https://github.com/chen310/BilibiliPotPlayer/issues/62>。

至少需要包含 `SESSDATA` 和 `bili_jct` 两项，否则只能拿到低画质甚至无法解析。

### 3. 在 PotPlayer 中指定配置路径

打开 PotPlayer → 按 `F5` → **扩展功能** → **媒体播放列表/项目** → 选中 `Bilibili` →
点击 **账户设置** → 在「配置文件路径」填入**完整绝对路径**，例如：

```
D:\Program Files\DAUM\PotPlayer\Extension\Media\PlayParse\Bilibili_Config.json
```

填写后点击「测试」，若能弹出账号信息即表示成功。

> 注意：受限于 PotPlayer 26.x 移除了旧式登录回调，此处的「测试」按钮可能无响应。
> 没关系——修复版插件已用 `EnsureConfig()` 自行读取配置文件，不依赖这个回调。
> **每次修改配置文件后都需要重启 PotPlayer。**

### 4. 配置转发服务自动启动（推荐）

编辑 `Bilibili_Config.json`，把 `proxyAutoStart` 填成 `launch.bat` 的**完整路径**：

```json
"proxyAutoStart": "C:\\PotPlayer-Bili\\proxy\\launch.bat"
```

> 路径中的反斜杠要写两次（JSON 转义规则）。

填写后即形成完整的生命周期绑定：

| 时机 | 行为 |
|---|---|
| PotPlayer 启动 | 插件在 `OnInitialize` 中先探测 `/ping`，未运行则用 `cmd /c` 调 `launch.bat` 拉起（`pythonw` 无窗口） |
| PotPlayer 正常关闭 | 插件在 `OnFinalize` 中请求 `/shutdown`，服务立即退出 |
| PotPlayer 崩溃 | 服务内置看门狗每 5 秒检测一次进程，连续 2 次未找到即自行退出（约 25 秒内） |

服务启动后有 15 秒宽限期才启用看门狗，避免播放器初始化慢时被误杀。

**因此不需要设置开机自启** —— 播放器不开，服务不占任何资源。

> 如果 `pythonw.exe` 不在 PATH 中，请编辑 `launch.bat`，把 `set PYTHONW=pythonw` 改成完整路径：
> ```bat
> set PYTHONW=D:\python\pythonw.exe
> ```

### 5. 验证服务状态

打开 PotPlayer 后，浏览器访问 <http://127.0.0.1:18999/ping>，返回 `pong` 即服务已就绪。

如需脱离播放器单独调试服务：

```bat
python proxy\bili_proxy.py --no-watch
```

`--no-watch` 会禁用看门狗，服务不会因 PotPlayer 未运行而自动退出，需按 `Ctrl+C` 手动结束。

### 6. 开始播放

- 直接把 B站链接拖进 PotPlayer，或按 `Ctrl + U` 粘贴链接
- 合集链接（不带 `?p=`）会解析出全部分P 列表
- 单集链接（带 `?p=N`）直接播放该集

---

## 五、配置项说明

| 配置项 | 默认值 | 说明 |
|---|---|---|
| `cookie` | `""` | B站账号 Cookie，必填 |
| `forceMuxed` | `true` | `true` 走音视频合一的 mp4，声音必定正常，画质上限 1080P<br>`false` 走 DASH 分离流，画质更高但 PotPlayer 26.x 下可能无声 |
| `danmaku.enable` | `false` | 弹幕开关。默认服务器已失效，未换可用服务器前请保持 `false` |
| `danmaku.server` | `""` | 弹幕服务器地址，需自行部署或寻找可用实例 |
| `showRecommendedVideos` | `true` | 播放单集时是否在列表中附加推荐视频 |
| `debug` | `false` | **正常使用保持 `false`**（不弹控制台）。设为 `true` 则播放时弹出解析日志，排查问题用 |
| `proxyAutoStart` | `""` | `launch.bat` 的完整路径。填写后服务随 PotPlayer 启停；留空则需手动启动服务 |
| `cookieFile` | `""` | `bili_auth.json` 的路径。填写后优先读取自动续期的最新 Cookie |

### 画质与声音的取舍

B站 对同一视频会提供多档码率。实测同一 1080P 视频：

```
DASH 分离流 (forceMuxed=false)  →  视频流 133 kbps + 音频流 127 kbps
durl 合一流 (forceMuxed=true)   →  单文件 265 kbps（含音视频）
```

屏幕录制类内容（如编程教程）B站 压缩很激进，133 kbps 的 1080P 本身就偏糊。
`forceMuxed=true` 的 265 kbps 反而是更高的整体码率，且不存在无声问题。

若播放真 4K / HDR 内容需要更高画质，可将 `forceMuxed` 改为 `false`，
但需自行确认音轨是否正常。

---

## 六、故障排查

| 现象 | 检查项 |
|---|---|
| 提示「服务器已关闭或地址错误」 | ① 转发服务是否在运行（访问 `/ping`）② Cookie 是否失效 |
| 有画面没声音 | `forceMuxed` 是否为 `true` |
| 播不了第 2 集及以后 | 确认插件文件已更新为新版（文件大小应约 66 KB） |
| 完全没反应、列表也解析不出 | 插件未加载。检查 `Extension\Media\PlayParse\` 下文件名是否正确（注意空格和大小写），并确认 PotPlayer 中已启用该扩展 |
| 想确认解析过程 | 把 `debug` 改为 `true`，播放时会弹出控制台，可见 `request:` / `result:` / `url:` / `proxy-id:` 等日志 |
| `proxy-id` 没有出现 | 转发服务未启动，插件已回退到直连模式 |

### 关键日志含义

```
Playitem path: https://www.bilibili.com/video/BVxxxx?p=1   ← 收到播放请求
request: https://api.bilibili.com/x/web-interface/view?...  ← 请求视频信息
result: OK                                                  ← 请求成功
request: https://api.bilibili.com/x/player/playurl?...      ← 请求播放地址
result: OK
url: https://upos-sz-xxx.bilivideo.com/....mp4?....         ← 解析出的真实地址
proxy-id: 1                                                 ← 已注册到转发服务
```

看到 `proxy-id` 就说明走的是转发通道，播放应正常。
若显示 `proxy: service down -> direct url`，则是服务没启动。

---

## 七、已知限制

1. **画质上限 1080P** —— 受 `forceMuxed=true` 限制，不支持 4K/HDR/杜比视界
2. **弹幕不可用** —— 原弹幕服务器域名已失效，需自行部署替代服务
3. **长视频可能只播第一段** —— `durl` 模式下若 B站 把视频切成多段，插件只取第一段。
   实测 7 分钟左右的视频为单段，超长视频（如电影）可能受影响
4. **依赖转发服务** —— 服务未运行时无法播放（会自动回退到直连，但直连会 403）
5. **Cookie 会过期** —— SESSDATA 有效期约半年，过期后需重新获取

---

## 附录 A：Cookie 自动续期

Cookie（SESSDATA）有效期约 30 天，过期后画质会掉到 **360P**。
本方案通过 `refresh_token` 自动续期，**长期免维护**。

### 一次性扫码登录

```bat
cd proxy
python bili_login.py qr      :: 生成二维码
python bili_login.py poll    :: 确认登录，保存凭证
```

用手机 B站 APP 扫码确认。成功后得到：

| 产物 | 位置 | 作用 |
|---|---|---|
| Cookie | `bili_auth.json` | 插件优先读取 |
| `refresh_token` | `bili_auth.json` | 自动续期的钥匙 |

### 自动续期机制

```
bili_proxy.py 启动（跟随 PotPlayer）
   └─> bili_cookie_refresh.maybe_refresh()
         ├─ 距上次刷新 < 7 天 → 跳过
         └─ 超过 7 天 → 调 B站 刷新接口换新
               ├─ 成功 → 更新 bili_auth.json
               └─ 失败 → 记录，下次重试
```

**关键设计**：刷新结果写到**用户目录**（`bili_auth.json`），
插件通过 `cookieFile` 配置项优先读取它 —— **全程不需要提权**。

```json
"cookieFile": "C:\\Users\\\\<you>\\\\bili-proxy\\\\bili_auth.json"
```

### 为什么画质掉到 360P

```
fnval=1  (durl 音视频合一) → 未登录时 B站 只给 360P
fnval=4048 (DASH 分离流)   → 未登录也能给 720P
```

`forceMuxed=true` 走 durl 合流（保证有声音），但 SESSDATA 一失效就被卡在 360P。
登录恢复后即回到 1080P。

### 注意事项

1. `refresh_token` 本身有效期约 **一年**，到期需重新扫码
2. 刷新失败通常意味着已过期，需重新执行 `bili_login.py qr`
3. 刷新间隔设为 7 天（SESSDATA 有效 30 天，留足余量）
4. 状态记录在 `bili_refresh_state.json`，可删除强制立即刷新

---

## 八、免责声明

本项目为 [chen310/BilibiliPotPlayer](https://github.com/chen310/BilibiliPotPlayer) 的兼容性修复分支，
仅用于个人学习与本地播放便利，不得用于任何商业用途或大规模抓取。
所有视频内容的版权归 B站 及原上传者所有。请遵守 B站 用户协议。
