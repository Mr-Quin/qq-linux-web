# qq-linux-web

在浏览器里使用 QQ，并把重要消息推送到 Discord、Telegram、ntfy 等地方。

一个 Docker 镜像，跑的是腾讯官方的 Linux QQ 客户端，打开网页就能用。放在 NAS、家里的服务器或 VPS 上，手机、平板、任何一台电脑都能随时登录同一个 QQ，消息通知还能转发到你常用的 App。

## 为什么用它

- **官方客户端**：镜像里就是腾讯发布的 Linux QQ，没有修改、没有注入、不走第三方协议。账号风险和在电脑上登录 QQ 一样。
- **打开网页就能用**：只有 QQ 一个窗口，没有多余的桌面。自带登录页面，可以设置用户名和密码。
- **消息通知转发**：QQ 弹出的通知可以转发到 Discord、Telegram、ntfy、邮件等几十种服务（基于 [Apprise](https://github.com/caronc/apprise)）。
- **网页设置页**：在 `/notify/` 页面选择转发哪些聊天、忽略哪些群、按关键词转发（比如 `@我`），每个推送地址都可以一键测试。
- **自动跟进新版本**：每天检查 QQ 是否有新版本，有就自动构建、测试、发布新镜像。

## 快速开始

1. 准备一个目录，生成固定的 machine-id：

   ```bash
   mkdir qq && cd qq
   cat /proc/sys/kernel/random/uuid | tr -d - > machine-id
   ```

2. 下载 [`docker-compose.yml`](docker-compose.yml)，把 `WEB_AUTHENTICATION_PASSWORD` 改成你自己的密码，然后启动：

   ```bash
   docker compose up -d
   ```

3. 打开 `https://服务器IP:5800`。镜像用的是自签名证书，浏览器提示不安全时选择继续访问即可（也可以放在反向代理后面，见下文）。

4. 输入你设置的用户名和密码，用手机 QQ 扫码登录。**记得勾选「自动登录」**，这样容器重启后不用再扫码。

## 保持登录

QQ 会根据机器的 MAC 地址和 machine-id 判断是不是新设备，换了就要在手机上重新确认登录。所以 `docker-compose.yml` 里固定了这两样：

- `mac_address`：随便写一个固定值，不要和局域网里其他设备重复。
- `machine-id`：第一步生成的文件，不要删。

迁移到别的机器时，把 `data` 目录、`machine-id` 文件和 MAC 地址一起带走就行。

另外，QQ 的设置里有跳过手机确认的登录选项，配合「自动登录」基本不用再碰手机。有用户反馈这个选项偶尔会自己关掉，如果又开始要求手机确认，重新打开即可。

## 消息通知转发

打开 `https://服务器IP:5800/notify/`（和 QQ 共用同一个登录）：

| 功能 | 说明 |
|---|---|
| 推送地址 | 填 [Apprise URL](https://github.com/caronc/apprise/wiki)。Discord 的 Webhook 地址可以直接粘贴。保存后密钥会被隐藏，每个地址都有「Test」按钮 |
| 聊天 | 列出所有发过通知的聊天，每个可以设为转发、忽略或默认。也可以勾选「转发所有聊天」 |
| 关键词 | 「总是转发」：比如 `@我`，被 @ 时即使在忽略的群里也会转发。「总是丢弃」：比如 `广告` |
| 试一试 | 输入聊天名和内容，看会不会被转发，未保存的修改也能测试 |

规则从上到下，第一条匹配的生效：

1. 包含「总是丢弃」的关键词 → 丢弃
2. 包含「总是转发」的关键词 → 转发
3. 聊天被设为忽略 → 丢弃
4. 聊天被设为转发，或勾选了「转发所有聊天」→ 转发
5. 其他 → 丢弃

设置保存在 `data/notify-forward.json`，也可以直接编辑这个文件，修改后立即生效，不用重启。

### 需要知道的几点

- **只转发通知内容**：也就是聊天名和一小段文字预览，图片和文件不会转发。程序不读取聊天记录。
- **免打扰的群不会转发**：QQ 里设为「接收消息但不提醒」或「屏蔽群消息」的群不会弹通知，自然也转发不了。想转发就在 QQ 里改成「接收并提醒」。
- **网页开着时暂停转发**：QQ 只有在窗口不显示时才会发通知。所以有人打开网页时，QQ 正常显示；网页全部关掉 10 秒后，QQ 自动隐藏到后台，开始转发通知。
- **只能单向**：只能把 QQ 的通知转出去，不能从 Discord 等地方回复 QQ 消息。

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `USER_ID` / `GROUP_ID` | 运行 QQ 的用户和组 ID，决定 `data` 目录的文件归属 | `1000` |
| `TZ` | 时区 | `Etc/UTC` |
| `WEB_AUTHENTICATION` | 设为 `1` 开启网页登录页 | `0` |
| `WEB_AUTHENTICATION_USERNAME` / `WEB_AUTHENTICATION_PASSWORD` | 网页登录的用户名和密码 | 无 |
| `SECURE_CONNECTION` | 网页使用 HTTPS。通知转发依赖它，请保持开启 | `1` |
| `WEB_NOTIFICATION` | 接收 QQ 的通知，同时在浏览器里弹出。通知转发依赖它，请保持开启 | `1` |

更多选项（分辨率、深色模式等）见基础镜像 [jlesage/baseimage-gui](https://github.com/jlesage/docker-baseimage-gui) 的文档。

## 放在反向代理后面

容器的 5800 端口提供 HTTPS（自签名证书）。反向代理连接后端时需要使用 `https`，并忽略证书校验。网页的远程画面使用 WebSocket，代理需要支持。

以 Traefik 为例：

```yaml
labels:
  - traefik.http.services.qq.loadbalancer.server.port=5800
  - traefik.http.services.qq.loadbalancer.server.scheme=https
```

并在 Traefik 里开启 `--serversTransport.insecureSkipVerify=true`。

## 更新

```bash
docker compose pull && docker compose up -d
```

登录状态和聊天记录都在 `data` 目录里，更新不会丢失。

## 常见问题

**怎么输入中文？**
容器里没有中文输入法。可以在电脑上打好字，通过网页侧边栏的剪贴板粘贴进去。

**和 linuxserver 的 webtop 有什么区别？**
webtop 是一整个 Linux 桌面。这个镜像只跑 QQ 一个程序，更轻，打开就是 QQ，还多了通知转发。

**会被封号吗？**
这里运行的是官方客户端，没有任何修改，和你在 Linux 电脑上用 QQ 没有区别。但不保证腾讯以后不会改变策略。

**支持 ARM 吗？**
暂时只有 x86_64（amd64）。

## 声明

本项目与腾讯无关。QQ 是腾讯公司的软件和商标，镜像中包含的是从腾讯官网下载、未经修改的 Linux QQ 安装包。本仓库自身的代码使用 MIT 许可证，不包括 QQ 本身。请仅用于个人用途，并遵守 QQ 的用户协议。
