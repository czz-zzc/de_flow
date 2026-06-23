# run_de——芯片设计流程管理工具

`run_de` 为 VCS、Verdi、SpyGlass、Design Compiler 和 Formality 提供统一的命令行入口。

整体设计遵循清晰的职责边界：Python 负责流程调度，设计人员负责维护静态 TCL 脚本。

完整的设计原理、模块职责和扩展约束见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

## 项目架构

```text
run_de                       轻量级命令行入口
run_de_config.yaml           工程与工具配置
requirements.txt             Python 依赖

deflow/
├── cli.py                   命令行解析与错误处理
├── config.py                配置展开及当前流程校验
├── runner.py                filelist、运行目录与进程管理
├── context.py               生成纯数据 run_context.tcl
└── flows.py                 流程注册与工具适配

tcl/
├── common/run_de_common.tcl 公共 TCL 初始化逻辑
├── spyglass/common.tcl      SpyGlass 公共流程
├── spyglass/lint.tcl        Lint 入口与检查目标
├── spyglass/cdc.tcl         CDC 入口与检查目标
├── dc/syn.tcl               综合流程
└── formality/fm.tcl         形式验证流程

tests/                       Python 与 TCL 自动化测试
```

各部分职责如下：

- Python：处理命令行参数、配置校验、输入文件查找、工作目录、日志、进程执行和退出码。
- TCL：处理 EDA 命令、methodology、检查目标、约束和报告生成。
- YAML：保存工程路径、工具名称、编译选项和工程相关的宏定义。

Python 不会动态生成 EDA 流程逻辑，只会为每次运行生成一个纯数据文件 `run_context.tcl`，然后通过环境变量 `RUN_DE_CONTEXT` 将其传递给对应的 TCL 脚本。

## 环境准备

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

设置工程根目录，并加载相应的 EDA 工具环境：

```bash
export PROJ_ROOT=/path/to/project
```

然后根据实际工程修改 `run_de_config.yaml` 中的路径、工具名称和选项。

配置文件支持以下变量：

- `PROJ_ROOT`：工程根目录，必须由用户设置。
- `RUN_DE_HOME`：`run_de` 所在目录，由程序自动设置。

如果配置中引用的外部环境变量不存在，程序会直接报错，不会使用空路径继续运行。

## 使用方法

### 查看可用 Design

列出 `project.filelist_path` 目录下所有可直接作为 `-d` 参数使用的主 filelist：

```bash
run_de -list
```

也可以使用标准长选项：

```bash
run_de --list
```

程序只扫描 filelist 根目录下的 `*.f`，并自动排除公共 filelist、子目录文件和名称不合法的 filelist。

### VCS 编译

```bash
run_de compile -d top_module
```

### Verdi 查看代码

```bash
run_de verdi -d top_module
```

### SpyGlass Lint

```bash
run_de lint -d top_module
```

### SpyGlass CDC

```bash
run_de cdc -d top_module
```

指定一个或多个 black-box 模块：

```bash
run_de cdc -d top_module -b async_fifo,memory
```

启动 SpyGlass GUI：

```bash
run_de cdc -d top_module -gui
```

批处理模式完成后会主动退出 `spyglass -shell`；GUI 模式不会执行退出操作，会保留工具窗口。

### Design Compiler 综合

```bash
run_de syn -d top_module
```

### Formality 等价性检查

```bash
export RUN_DE_IMPL_NETLIST=/path/to/top_module_syn.v
run_de fm -d top_module
```

同时在 reference 和 implementation 中设置 black box：

```bash
run_de fm -d top_module -b memory,analog_macro
```

当前 Formality TCL 通过 `RUN_DE_IMPL_NETLIST` 获取待验证的综合网表。

### 使用其他配置文件

`--config` 必须写在子命令之前：

```bash
run_de --config project.yaml lint -d top_module
```

## Filelist 规则

程序根据 `run_de_config.yaml` 中的 `project.filelist_path` 查找：

```text
<filelist_path>/<design>.f
```

例如：

```bash
run_de lint -d cpu_top
```

对应的主 filelist 为：

```text
<filelist_path>/cpu_top.f
```

公共设计 filelist 和公共仿真 filelist 由以下配置控制：

```yaml
project:
  common_file: "${PROJ_ROOT}/trunk/design/filelist/common.f"
  common_sim_file: "${PROJ_ROOT}/trunk/design/filelist/sim/common_sim.f"
```

## 库清单

SpyGlass 使用 Liberty `.lib`，DC 和 Formality 共用 Synopsys `.db`，因此配置两个清单入口：

```yaml
project:
  spyglass_lib_file: "${PROJ_ROOT}/trunk/bin/deflow/spyglass_lib.yaml"
  common_db_file: "${PROJ_ROOT}/trunk/bin/deflow/common_db.yaml"
```

`spyglass_lib.yaml`：

```yaml
libraries:
  - "/pdk/lib/stdcell_ss.lib"
```

`common_db.yaml`：

```yaml
libraries:
  - "/pdk/db/stdcell_ss.db"
```

相对路径以各清单所在目录为基准。清单不存在时跳过库加载；清单存在但其中的库文件不存在时直接报错。

Python 将当前工具需要的路径写入 `run_de(library_files)`：

- SpyGlass 从 `spyglass_lib.yaml` 取 `.lib`，使用 `read_file -type gateslib`。
- DC 从 `common_db.yaml` 取 `.db`，设置 `target_library` 和 `link_library`。
- Formality 与 DC 共用 `common_db.yaml`，使用 `read_db`。

程序会在启动工具前校验扩展名：SpyGlass 只接受 `.lib`/`.lib.gz`，DC 和 Formality 只接受 `.db`。TCL 流程本身也有异常保护，批处理发生 FATAL 时会以非零状态主动退出，不会停留在交互 shell。

## 运行产物

每次执行都会创建一个独立且可追溯的运行目录：

```text
<work_path>/<design>_<flow>_<timestamp>/
├── command.txt              实际执行的工具命令
├── resolved_config.yaml     本次运行使用的配置快照
├── run.log                  工具标准输出和错误输出
├── run_context.tcl          TCL 流程使用的数据上下文
├── reports/                 工具报告
└── outputs/                 网表、SDC 等交付文件
```

`compile` 和 `verdi` 不使用 TCL，因此不会生成 `run_context.tcl`。

DC 综合生成的 `<design>_syn.v` 和 `<design>_syn.sdc` 保存在 `outputs/`，与 `reports/` 分开。

保存这些文件可以帮助定位问题，也可以使用同一份配置和上下文复现某次运行。

## TCL 维护方式

设计人员通常只需要修改 `tcl/` 目录：

- 修改 Lint goal：编辑 `tcl/spyglass/lint.tcl`。
- 修改 CDC goal：编辑 `tcl/spyglass/cdc.tcl`。
- 修改 SpyGlass 公共设置、报告和 methodology：编辑 `tcl/spyglass/common.tcl`。
- 修改综合流程：编辑 `tcl/dc/syn.tcl`。
- 修改 Formality 流程：编辑 `tcl/formality/fm.tcl`。
- 多个工具共用的初始化逻辑：放在 `tcl/common/run_de_common.tcl`。

不要在 `deflow/context.py` 中添加 EDA 命令。该文件只负责在 Python 和 TCL 之间传递运行数据。

当前 `syn.tcl` 已统一配置普通/拓扑模式核数、DesignWare `dw_foundation.sldb`、技术库 `target_library/link_library` 以及稳定的总线命名分隔符。寄存器优化、scan、UPF 和消息屏蔽仍由具体项目评估后添加。

## 配置校验

程序只校验当前执行流程需要的配置。例如执行：

```bash
run_de compile -d top_module
```

不会因为 CDC 或 Formality 的配置尚未完成而失败。

设计名必须符合以下格式；支持 `-b/--black-box` 的流程中 black-box 名称也必须符合该格式：

```text
[A-Za-z_][A-Za-z0-9_]*
```

## 自动化测试

执行全部测试：

```bash
python -m unittest discover -s tests -v
```

测试覆盖：

- 环境变量和配置校验。
- 按当前流程进行配置校验。
- 设计名称校验。
- filelist 查找规则。
- 工具退出码透传。
- `run_context.tcl` 数据生成。
- 静态 TCL 调用方式。
- TCL 文件语法完整性。

真实 EDA 工具的命令和 TCL 行为仍需在对应工具环境中进行 smoke test。
