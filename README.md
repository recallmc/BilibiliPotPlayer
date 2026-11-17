# BilibiliPotPlayer

适用于 PotPlayer 的 Bilibili 插件。如果配合[油猴脚本](https://greasyfork.org/zh-CN/scripts/461800-bilibilipotplayer)，可以直接在网页打开 PotPlayer 进行播放

---

## 本分支：PotPlayer 26.x 兼容性修复版

> 原插件最后更新于 **2025-05-22**，而 PotPlayer **26.x**（2026 年起）重构了 AngelScript 扩展系统。
> 原版在新版播放器上会出现：黑屏转圈、有画面没声音、「服务器已关闭或地址错误」、只有第一个分P能播、画质异常模糊。
>
> 本分支已针对 PotPlayer **26.10.21** 完成修复并实测通过。

**主要改动**

| 问题 | 修复方式 |
|---|---|
| 配置文件读不进来（`ServerLogin` 回调已被新版移除） | 改为 `EnsureConfig()` 懒加载，在解析入口直接读取 |
| B站 CDN 返回 403（PotPlayer 不发送 Referer） | 新增本地转发服务 `proxy/bili_proxy.py`，绕开播放器 header 机制 |
| 有画面没声音（DASH 音视频分离、音轨配对失败） | 新增 `forceMuxed` 开关，默认请求音视频合一的 mp4 |
| 第 2 集起播不了（失败请求把空 URL 混入画质列表） | 画质列表只保留最高档，不再插入空项 |
| 画质被误选成 360P | 同上，只提供当前最高画质 |
| 弹幕加载拖累播放 | 原弹幕服务器 `subtitle.chen310.repl.co` 域名已失效，默认关闭 |
| 转发服务需手动开关 | 绑定到播放器生命周期：启动时拉起、关闭时退出，崩溃后由看门狗兜底 |
| Cookie 过期后画质掉到 360P | 扫码登录一次 + `refresh_token` 自动续期，长期免维护 |

**快速开始**

```text
1. 复制插件文件到 PotPlayer 的 Extension\Media\ 对应目录（见下方「安装插件」）
2. 扫码登录获取 Cookie（推荐，一劳永逸）：
     cd proxy
     python bili_login.py qr      # 生成二维码，手机 B站 APP 扫码
     python bili_login.py poll    # 确认登录，自动保存凭证
   也可手动把 Cookie 填进 Bilibili_Config.json，但过期后需要自己更新
3. 编辑 Bilibili_Config.json，填好两项：
     proxyAutoStart  = proxy\launch.bat 的完整路径（注意反斜杠写两次）
     cookieFile      = bili_auth.json 的完整路径（启用自动续期）
4. 重启 PotPlayer，把 B站链接拖进去
```

转发服务会**随 PotPlayer 自动启停**，无需手动管理，也不需要设置开机自启：

| 时机 | 行为 |
|---|---|
| 播放器启动 | 插件自动拉起服务（`pythonw` 启动，无黑框） |
| 播放器关闭 | 插件通知服务退出 |
| 播放器崩溃 | 服务看门狗约 25 秒后自行退出 |

> 验证服务是否就绪：浏览器打开 <http://127.0.0.1:18999/ping>，返回 `pong` 即可。

**Cookie 自动续期**：服务启动后每 7 天自动刷新一次 Cookie（`refresh_token` 换新），
结果写入用户目录的 `bili_auth.json`，插件优先读取它。**长期使用无需手动更新 Cookie**。
详细说明见 [docs/FIX-PotPlayer-26.md](docs/FIX-PotPlayer-26.md) 的「附录 A」。

**完整文档**

原理解析、逐项改动说明、配置项解释、故障排查表、已知限制 → **[docs/FIX-PotPlayer-26.md](docs/FIX-PotPlayer-26.md)**

---

## 安装插件

[下载项目](https://github.com/chen310/BilibiliPotPlayer/archive/refs/heads/master.zip)

将项目 `Media/PlayParse` 路径下的 `MediaPlayParse - Bilibili.as`、`MediaPlayParse - Bilibili.ico` 和 `Bilibili_Config.json` 三个文件复制到 `{PotPlayer 安装路径}\Extension\Media\PlayParse` 文件夹下。

`MediaPlayParse - Bilibili.as` 提供了解析 `Bilibili` 链接的功能。

将项目 `Media/UrlList` 路径下的 `MediaUrlList - Bilibili.as` 和 `MediaUrlList - Bilibili.ico` 两个文件复制到 `{PotPlayer 安装路径}\Extension\Media\UrlList` 文件夹下。

`MediaUrlList - Bilibili.as` 提供了列出 `Bilibili` 常用链接的功能，使用方式为按下 <kbd>ctrl</kbd> + <kbd>U</kbd> 并选择要播放的项目，如下图所示

![UrlList](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/urllist.png)

## 登录

找到刚刚复制过去的配置文件 `Bilibili_Config.json`，填写 Cookie 等设置内容。 打开 PotPlayer，按 <kbd>F5</kbd> 打开选项，点击`扩展功能`下的`媒体播放列表/项目`，再点击 `Bilibili`，然后打开`账户设置`，填写配置文件路径，如 `D:\DAUM\PotPlayer\Extension\Media\PlayParse\Bilibili_Config.json`。每次修改完配置文件，可能都要重启 PotPlayer 才能生效。

![Settings](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/settings.png)

点击测试按钮，如果弹出账号信息，就说明登录成功。

![Test](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/test.png)

### Cookies 获取

[获取Cookie](https://github.com/chen310/BilibiliPotPlayer/issues/62#issuecomment-1841909583)

## 使用方法

### 播放视频/直播

将 Bilibili 链接拖到 PotPlayer，或者按 <kbd>ctrl</kbd> + <kbd>U</kbd> 粘贴 Bilibili 链接即可播放。可参考[视频](https://www.bilibili.com/video/BV1mM41177kT)

### 搜索

按 <kbd>ctrl</kbd> + <kbd>U</kbd>，在文件地址列表中选择`搜索`，然后到上面的输入框中替换关键词，最后回车即可

![Search](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/search.png)

### 跳过片头片尾

对于一些电视剧、番剧，能够跳过片头和片尾。具体设置为：在 PotPlayer 上点击鼠标右键，选择`播放`-`跳略播放`-`跳略播放设置`

![Skip_Settings](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/skip_1.png)

勾选`跳略播放`和`章节名称`，并在名称列表中追加`哔哩哔哩-片头`和`哔哩哔哩-片尾`两项，每一项之间用英文分号`;`隔开。

![Skip_Settings](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/skip_2.png)

### 在列表中显示缩略图

按 <kbd>F6</kbd> 打开播放列表，点击鼠标右键，点击`样式`，选择`显示缩略图`，即可显示视频的缩略图。

![Thumbnail](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/thumbnail.png)

### 创建自动更新的播放列表

按 <kbd>F6</kbd> 打开播放列表，点击新建专辑，起一个合适的专辑名称，选择外部播放列表，并填写相应的链接，再点击确定即可。这样就得到一个可以自动更新的列表。

![Create_Playlist](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/create_playlist_1.png)

![Create_Playlist](https://cdn.jsdelivr.net/gh/chen310/BilibiliPotPlayer/public/create_playlist_2.png)
