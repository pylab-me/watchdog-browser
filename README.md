# watchdog-browser

从 Postgres 拉取网站任务，使用 Playwright 定期刷新完整浏览器认证态，并把最新状态压缩后写回数据库。

当前实现已经不是“只刷新 cookies”，而是以 Playwright `storageState` 为主，覆盖：

- cookies
- localStorage
- IndexedDB
- sessionStorage

其中 `sessionStorage` 不在 Playwright `storage_state()` 默认持久化范围内，所以单独存一份快照。

## 刷新流程

每个任务执行时按下面的顺序运行：

1. 从数据库读取 `storage_state + session_storage`
2. 恢复到新的临时 Playwright 浏览器上下文
3. 打开 `site_url`
4. 等待页面稳定
5. 再访问 `reload_url or site_url`
6. 再等待页面稳定
7. 抓取最新 `storageState + sessionStorage`
8. 压缩后写回数据库
9. 成功则把 `next_poll_at` 推进 1 天；失败则推进 15 分钟

所有 Playwright 会话都使用临时用户目录，不复用本机固定 Chrome 用户目录。

## 数据库字段

表名：`cookie_refresh_tasks`

关键字段说明：

- `site_url`
  首次打开的页面地址。
- `reload_url`
  恢复状态后再次访问的锚点地址；如果为空，则回退到 `site_url`。
- `state_scope_url`
  `sessionStorage` 的采集和恢复作用域；如果为空，则回退到 `site_url`。
- `storage_state BYTEA`
  `context.storage_state(indexed_db=True)` 的 JSON，经 `zlib.compress(...)` 压缩后的二进制。
- `session_storage BYTEA`
  当前目标 origin 的 `sessionStorage` JSON，经 `zlib.compress(...)` 压缩后的二进制。
- `remark`
  给任务写备注，便于区分站点、用途或账号。
- `next_poll_at`
  下次调度时间。调度器会优先执行小于等于当前时间的任务。
- `refresh_interval_seconds`
  成功后的刷新周期，默认 `86400` 秒。
- `retry_interval_seconds`
  失败后的重试周期，默认 `900` 秒。

`storage_state` 解压后的结构类似：

```json
{
  "cookies": [],
  "origins": [
    {
      "origin": "https://example.com",
      "localStorage": []
    }
  ]
}
```

## 调度行为

- 成功刷新后：`next_poll_at = refreshed_at + 86400s`
- 刷新失败后：`next_poll_at = now + 900s`
- 调度器最多睡眠 15 分钟
- 如果数据库里存在更早的 `next_poll_at`，调度器会提前醒来
- 如果任务的 `next_poll_at <= now`，会立刻执行

## 数据库连接

连接风格对齐 [engine.py](/M:/CodeHub/watchdog-browser/engine.py)，使用：

- `sqlalchemy.create_engine(...)`
- `get_engine().connect()`

默认读取：

- `engine.py` 中的 `local_`

也支持环境变量覆盖：

- `WATCHDOG_BROWSER_LOCAL_DSN`

## 初始化数据库

执行：

```sql
psql -d watchdog_browser -f schema.sql
```

如果你之前已经落过旧版本表结构，需要迁移到当前字段：

- 删除旧的 `cookies` 主存储思路
- 增加 `reload_url`
- 增加 `state_scope_url`
- 增加 `storage_state`
- 增加 `session_storage`

当前标准结构以 [schema.sql](/M:/CodeHub/watchdog-browser/schema.sql) 为准。

## 首条任务初始化

首条记录不建议手填。直接用交互脚本人工登录一次，再把认证态落库。

命令：

```bash
python bootstrap_task.py --site-url https://example.com
```

脚本行为：

- 主线程启动 Playwright，非无头打开页面
- 输入线程监听终端命令
- 你手工完成登录、二次验证、跳转等操作
- 在终端输入 `capture` 后，脚本会把当前认证态直接写入数据库

可用命令：

- `status`
  查看当前页面 URL。
- `capture`
  抓取当前 `storageState + sessionStorage`，压缩后插入数据库。
- `quit`
  退出，不写数据库。

如果站点要求恢复状态后再进入特定页面触发 token 续期，可以在初始化时直接记录 `reload_url`：

```bash
python bootstrap_task.py ^
  --site-url https://example.com ^
  --reload-url https://example.com/account ^
  --state-scope-url https://example.com ^
  --remark "Liepin main account"
```

## 启动调度器

```bash
python run_worker.py
```

也支持直接运行源码入口：

```bash
python src\main.py
```

## 代码入口

- [bootstrap_task.py](/M:/CodeHub/watchdog-browser/bootstrap_task.py)
  根目录初始化脚本入口。
- [run_worker.py](/M:/CodeHub/watchdog-browser/run_worker.py)
  根目录调度器入口。
- [src/bootstrap_task.py](/M:/CodeHub/watchdog-browser/src/bootstrap_task.py)
  初始化逻辑。
- [src/refresher.py](/M:/CodeHub/watchdog-browser/src/refresher.py)
  调度与刷新逻辑。
- [src/db.py](/M:/CodeHub/watchdog-browser/src/db.py)
  Postgres 访问层。
- [src/state.py](/M:/CodeHub/watchdog-browser/src/state.py)
  `storage_state` / `session_storage` 压缩与解压。

## 工具函数

如果你需要把数据库里某条任务的 cookies 转成 HTTP 请求头，可直接使用：

```python
from src.db import TaskRepository

repo = TaskRepository()
headers = repo.build_headers_for_task(123)
```

返回结果是：

```python
{"Cookie": "sid=abc; uid=42"}
```

## 验证

已覆盖的基础验证：

```bash
python -m unittest discover -s tests -v
python -m compileall engine.py src tests bootstrap_task.py run_worker.py
```
