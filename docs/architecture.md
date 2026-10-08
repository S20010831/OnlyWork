# 扩展架构

## 数据流与职责

`main.App` 是装配入口：加载服务、配置和题库，连接界面信号，管理托盘和退出。业务逻辑不放在入口或绘制代码中。

```text
题库文件 → QuestionImporters → LibraryStore → QuizSession
                                       ↓           ↑
                                本地题库缓存       StudyController
                                                   ↙          ↘
                                          ReviewScheduler   ActionRegistry
                                                   ↑
                        RadialWidget 发出用户意图并读取 QuizSession
                        Overlay 管理定位、显示、计时和渐隐
```

| 层 | 模块 | 扩展职责 |
|---|---|---|
| 领域模型 | models、session | 不依赖 Qt；稳定身份、题目校验、答题状态与防重复提交 |
| 答题规则 | answers | 答案校验、选择切换、判断结果、显示名称与自动提交策略 |
| 导入与保存 | questions、library、storage | 注册文件格式、规范化保存、资产准备、原子写入 |
| 复习 | scheduler | 注入评分策略、间隔策略、时钟、随机源与存储路径 |
| 动作 | extensions、qt_actions | 注册动作与校验，分离操作含义和 Qt 执行方式 |
| 配置 | config、theme | 版本化配置、逐字段校验、透明颜色和交互参数 |
| 协调与界面 | controller、radial_widget、overlay、settings | 信号连接、展示、用户操作、自动切题及窗口生命周期 |

## 统一装配入口

使用一个自己的 Python 启动文件注册服务，再交给标准入口，以复用日志、单实例锁、托盘和退出清理：

```python
from main import main
from app.services import AppServices
from app.extensions import CallbackAction

services = AppServices()
services.actions.register(
    "lookup",
    CallbackAction(lambda value, host: host.show_info(f"查询结果：{value}")),
)

if __name__ == "__main__":
    raise SystemExit(main(services))
```

所有注册应在启动前完成，这样缓存题库加载、导入校验和运行时执行使用相同的服务。名称和文件后缀不能重复注册。这里使用明确的 Python 注册机制；不会自动执行题库中的代码或扫描并运行插件目录。

## 新增扩展动作

`ActionRegistry.register(name, handler)` 接收满足 `ActionHandler` 协议的处理器：

- `validate(value)`：校验动作内容；失败抛出 `ActionError`。
- `prepare(value, source_directory, data_directory)`：导入阶段处理资源并返回持久化内容。
- `execute(value, context)`：用户触发扩展动作时执行。

简单动作可以用 `CallbackAction(callback, validator=None)`，默认无需准备资源。需要复制资源的动作可实现自己的 prepare；内置 `AudioAction` 就是完整示例。

宿主 `ActionContext` 提供 `show_info(text)`、`open_url(url)`、`play_audio(path)` 和 `base_directory`，可在测试中替换。Qt 的播放器延迟创建并保留到退出；解析窗口支持复用，文本按纯文本显示。动作异常由控制器捕获，交给界面报告。

Excel 使用 `lookup:单词`，JSON 使用 `{"type": "lookup", "value": "单词"}`。自定义动作与内置动作通过相同路径保存、恢复和执行。

## 新增题库格式

```python
from pathlib import Path
from app.models import QuizQuestion


def read_custom(path: Path) -> tuple[QuizQuestion, ...]:
    # 在这里解析并返回领域模型。格式错误抛出 QuestionFormatError。
    ...


services.importers.register(".custom", read_custom)
```

导入器返回非空题目元组，ID 不重复。设置中的文件筛选器由注册表生成，无需改界面。LibraryStore 统一完成规则/动作校验、资源准备和缓存保存。JSON 缓存格式带 version；只接受当前支持的版本。

## 新增答题规则

`AnswerRule` 提供：

- `label`：圆盘中心显示的题型名称。
- `auto_submit`：点击选择后是否自动判断。
- `validate(question)`：规则对题目的要求。
- `toggle(selected, option_id)`：返回新的选中编号集合。
- `evaluate(question, selected)`：返回是否正确。

例如增加需要手动确认的单选练习模式：

```python
from app.answers import ChoiceRule

services.answers.register(
    "practice",
    ChoiceRule(label="练习", auto_submit=False, single=True),
)
```

在 JSON 或自定义导入器中指定 `"mode": "practice"`。Excel 内置导入器只按答案数量判断单选与多选。当前渲染器支持 3～6 项选择题；填空、拖拽等新的交互形式需要增加对应领域数据与渲染器，现有答题规则接口不冒充这些交互。

QuizSession 对一次选择状态只提交一次；正确后锁定选项。答错可修改选择后再提交。持久化失败会回退本次提交状态，允许重试。切题、导航和换题库均清理选择状态；导航和换题库取消自动切题计时。

## 替换复习策略

评分和间隔分开注入：

```python
from app.scheduler import SpacedReviewPolicy


class MyPriority:
    def score(self, state, current):
        return 1.0 + state.incorrect  # 必须是有限的正数


services.review_strategy = MyPriority()
services.spacing_policy = SpacedReviewPolicy(intervals=(1, 2, 5, 10))
```

也可实现 `SpacingPolicy.update(state, correct, current)`，自行设置连续正确次数、复习时间与冷却时间。ReviewScheduler 统一维护答题计数和持久化；构造函数可传入 path、clock、rng，方便确定性测试。默认选题排除当前题，自动和手动导航都更新显示记录。

## 身份、存储和测试

显式 ID 在同一题库中应唯一且保持稳定。LibraryStore 根据源文件规范化绝对路径生成题库标识并写入缓存；ReviewScheduler 按题库分组保存状态，切换题库时选择对应状态集合。自动 ID 取题目、题型、按编号排序的选项和正确答案的 SHA-256；不依赖题库行号、显示顺序、解析文字或资源路径。同一题库中的相同学习内容因而共享复习记录，不同题库相互隔离。

ReviewScheduler 在同一个复习文件的 positions 中，按题库保存 StudyPosition（question_id、completed）。mark_shown 保存未完成位置，record 同时保存计数和完成状态；resume 按 ID 恢复未完成题，已完成或已删除的题通过注入的复习策略选择下一题。位置缺失时使用有效题目的最近显示时间；没有显示记录时从第一题开始。控制器在保存成功后更新题目；重启清空临时选择与反馈，不重新提交答案。

导入使用 ReviewScheduler.transaction 暂缓中途写入，并备份调度状态；题库缓存写入成功后才提交复习状态。外层 preserve_file 在后续步骤失败时原子恢复原缓存，两者成功后再更新界面。缓存未改变时不重复写入；恢复失败会报告错误并保留原文件备份，清理备份失败只记日志。这是应用运行期间的异常回滚；两个文件仍各自原子替换，不保证进程在两次替换之间被强制终止时整体回滚。

LibraryStore 保存规范化题目，而不是启动时重新读取原 Excel。音频按内容哈希去重，复制进 data/assets。所有 JSON 保存都使用同目录临时文件、flush、fsync 和原子替换。

`App(application, data_dir=..., services=..., start_services=False)` 用于嵌入和集成测试。关闭真实服务后，仍可测试完整窗口、设置和控制器。纯领域测试不需要创建 Qt 窗口；Qt 测试使用 offscreen 平台、模拟媒体/浏览器宿主和临时目录。

保持新业务逻辑在可独立测试的服务中；UI 通过信号传递意图，入口通过 AppServices 完成装配。这样新增动作、格式和复习算法时，不需要同时修改圆盘、设置窗口和主控制器。

Excel 使用 A～F 独立选项列。内置导入器汇总行级校验问题，LibraryStore 合并规则与扩展校验，失败时不替换活动题库。
info 通过问号悬停展示 ExplanationBubble；方向由 bubble_position 按屏幕可用空间选择，离开立即隐藏。气泡是透明 QWidget，只绘制文字和与圆盘一致的细边框，不强制提高主题透明度；按内容高度展开，长文限制高度并通过悬停位置上的滚轮翻阅。ThemedTextDialog 用于需要完整阅读的导入报告。

option_layout 根据扇区路径扣除中心卡片和边缘留白，计算一到四行的安全文字区域，再按实际内容选择排版。换行使用 Qt 的单词和字形边界，并优先保留标点分隔；只有最后一行溢出才省略。几何区域按选项数和字体行高缓存，文字排版按当前题目和字体缓存。选项全文复用 ExplanationBubble，优先向对应扇区外侧展开；空间不足时自动换方向，不覆盖轮盘。只有内容仍被省略时显示，不再使用字符数阈值。
