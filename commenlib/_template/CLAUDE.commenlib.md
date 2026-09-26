# commenlib 通用模块说明

本项目已集成 commenlib 通用模块（激活验证 + 更新检查 + 单实例锁 + 编译打包）。

## 接入只需 3 步

1. 把 `commenlib/` 整目录拷贝到项目根（或 `git submodule add`）
2. 复制 `commenlib/_template/project.yaml` 到项目根目录，填字段
3. 在 `main.py` 中 `from commenlib import AppInit` 并按下文示例使用

> 宿主项目不再需要任何 `app_init.py` 文件 —— 全部逻辑已迁入 `commenlib/__init__.py`。

## 唯一需要修改的文件：`project.yaml`

| 字段 | 说明 |
|------|------|
| `app.name` | 软件名称（标题栏、EXE 文件名） |
| `app.version` | 版本号，格式 `1.0.0` |
| `license.server_url` | 激活服务端地址 |
| `license.product_id` | 产品 ID（英文，用作数据目录名） |
| `update.check_url` | version.json 的 HTTP 地址 |
| `build.main_script` | 主程序入口文件，默认 `main.py` |
| `build.cython_sources` | 宿主项目自身需编译为 .pyd 的 .py 文件列表（**无需**列 commenlib 自己的源，由 commenlib 自编译） |

## 目录结构

```
项目根目录/
├── project.yaml          # 唯一需要修改的配置文件（从 _template 复制）
├── main.py               # from commenlib import AppInit
└── commenlib/
    ├── __init__.py       # 暴露 AppInit（无需宿主再写 app_init.py）
    ├── buildsystem/      # 编译打包（Cython + PyInstaller）
    ├── license_guard/    # 激活验证
    ├── update_guard/     # 自动更新
    └── singleinstance_guard/  # 单实例锁
```

## 在 main.py 中集成（异步流程）

```python
from commenlib import AppInit

def main():
    app = AppInit()                # 只读配置，不自动激活
    # ... 原有的单实例检查 / crash hook / state 预加载 ...
    root = tk.Tk()
    root.withdraw()                # 启动时隐藏，避免空白闪烁

    def on_license_ok():
        launch_main_app(root, app)          # 激活通过后进入主界面
        app.start_periodic_verify(root)     # 持续运行期间每24h 后台验证，含永久卡

    def on_license_fail(msg):
        logger.warning(f"授权验证未通过: {msg}")

    app.verify_license_async(root, on_license_ok, on_fail=on_license_fail)

    root.mainloop()
```

## 主窗口中暴露给用户的菜单

```python
# "检查更新" 菜单项 → 用户点击后后台异步检查
self.app.check_update_async(self.root)

# "关于 / 授权信息" 菜单项 → 弹窗展示机器码 / 卡类型 / 到期时间
self.app.show_license_info(self.root)
```

## AppInit 对外接口速查

| 方法 | 说明 |
|------|------|
| `verify_license_async(root, on_success, on_fail=None)` | 后台验证授权，通过后回调 on_success；未激活/失败时主线程弹激活窗 |
| `start_periodic_verify(widget)` | 启动后台定期授权验证（每 24h），需在授权通过后调用 |
| `check_update_async(widget)` | 手动触发后台检查更新 + 弹窗（用户点击菜单时调用） |
| `show_license_info(widget)` | 弹窗展示当前授权状态 |
| `name` / `version` | 来自 project.yaml 的应用名与版本号 |
| `license_client` | LicenseClient 实例，授权通过后可用 |

## 构建打包

```bash
python commenlib/buildsystem/build_all.py
```

构建流程：清理 → Cython 编译 .pyd（自动包含 commenlib 自身）→ PyInstaller 打包 EXE → 清理临时文件

> commenlib 内部的 `license_guard / update_guard / singleinstance_guard` 子模块会被自动编译为 .pyd，
> 宿主**无需**在 `project.yaml.build.cython_sources` 中列出。
> `__init__.py`、`config.py` 和示例不参与自动 Cython 编译。编译提高逆向成本，不构成防破解保证。

## 授权兼容与安全边界

- 激活窗口与 `AppInit.license_client` 共用同一实例，激活后立即更新授权状态。
- 授权模块导入失败、服务地址无效或产品标识为空时会报错，不会直接放行业务入口。
- 仅接受 HMAC 验签通过且与当前机器码一致的凭证；支持无 `cred_version` 的旧签名格式。
- 无签名 JSON、签名损坏的凭证需要重新联网激活，不能取得离线宽限。
- 旧路径迁移也必须验签，保留旧文件，不再从凭证覆盖机器码。
- 新路径存在时不回退旧副本；撤销后保存空授权状态，防止重启时再次迁移旧授权。
- 普通期限卡允许离线时间严格小于配置天数；默认 7 天，0 表示禁用宽限。
- 试用卡与永久卡必须联网。响应格式异常不进入宽限；连接失败、超时和服务端 5xx 仍可走宽限。
- 缺失或无法解析定期验证时间时立即验证，不再持续跳过。
- 兼容现有服务端协议：缺少响应 `sig` 时仍接受，因此尚未强制服务端响应签名。
- 凭证是签名 JSON，不是加密文件；机器码和凭证都在本地，不能承诺阻止整个目录复制或本地逆向。

## 单实例与更新行为

单实例需要宿主单独调用，默认保留已有进程并返回 `False`。
`kill_stale_in_frozen=True` 为显式强杀选项，会结束同名 EXE 及其子进程，不能用来判断旧实例是否异常。

更新模块只检查版本并打开下载链接，不覆盖程序。HTTP 非 200 返回错误，不再提示已是最新版。

## 构建清理范围

- 默认构建在任何步骤之前验证宿主 `project.yaml`、入口和 `commenlib` 目录布局。
- 公共库仓库单独克隆时不能直接执行默认完整构建；缺少宿主时会提前停止。
- Cython 的 C 文件、编译临时文件和 PyInstaller 工作文件放入 `.commenlib-build`。
- 默认清理仅针对该专用目录，保留 `dist`、宿主 `build`、原生 C 文件和原地编译的 `.pyd`。
- 自定义清理禁止 `file_extensions` 全目录扫描，递归目录名仅支持 `__pycache__`。
- 执行与预览使用同一目标校验：禁止项目根、越界路径、虚拟环境、保护目录和链接/junction。
