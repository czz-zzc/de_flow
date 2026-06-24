# run_de 架构说明

本文面向维护者，描述 `run_de` 的整体架构、模块职责、数据流、运行策略和扩展约束。

## 设计目标

`run_de` 为芯片设计常用工具提供统一入口：

- VCS compile
- Verdi
- SpyGlass lint
- SpyGlass CDC
- Design Compiler synthesis
- Formality equivalence check

核心目标：

- Python 只管理“如何启动流程”，不承载 EDA 业务逻辑。
- TCL 只管理“工具内部做什么”，由设计/CAD 人员维护。
- YAML 只描述“当前工程路径、工具和选项是什么”。
- 每次运行保留命令、配置、上下文、日志、报告和输出，便于复现。
- 新增 flow 时尽量只增加配置、TCL、注册和测试。

一句话原则：

> Python 负责调度，TCL 负责工具流程，YAML 负责工程差异。

## 总体分层

```text
User CLI
  │
  ▼
deflow.cli
  │  解析参数、校验设计名、选择 flow
  ▼
deflow.config
  │  读取 YAML、展开环境变量、按当前 flow 校验
  ▼
deflow.flows
  │  选择 flow adapter
  ▼
deflow.runner
  │  准备 filelist、运行目录、命令、日志、进程
  ▼
deflow.context
  │  生成 run_context.tcl
  ▼
static TCL
  │  执行 EDA 命令、goal、report、output
  ▼
EDA tool
```

## 目录与职责

```text
run_de
run_de_config.yaml

deflow/
├── cli.py
├── config.py
├── context.py
├── flows.py
└── runner.py

tcl/
├── common/run_de_common.tcl
├── spyglass/common.tcl
├── spyglass/lint.tcl
├── spyglass/cdc.tcl
├── dc/syn.tcl
└── formality/fm.tcl
```

### Python

Python 负责：

- 命令行参数解析。
- 当前 flow 配置加载和校验。
- 环境变量展开。
- filelist 和库清单解析。
- 运行目录创建。
- `command.txt`、`resolved_config.yaml`、`run_context.tcl`、`run.log` 管理。
- 进程启动和退出码返回。

Python 不负责：

- 拼接 EDA 业务 TCL。
- 决定 SpyGlass goal 细节。
- 决定 DC compile 策略。
- 决定 Formality match/verify/report 策略。

### TCL

TCL 负责：

- 工具 setup。
- 读 RTL、读库、读约束。
- goal/methodology。
- synthesis、match、verify。
- report 和 output 写出。
- 工具版本兼容处理。

### YAML

YAML 负责：

- 工程路径。
- 工具可执行名。
- flow 工作目录。
- flow 选项。
- 工程宏定义。
- 可选 hook 脚本路径。

## 配置加载与校验

`deflow.config.load_config()` 会：

1. 读取 `run_de_config.yaml` 或 `--config` 指定的文件。
2. 自动注入 `RUN_DE_HOME`。
3. 展开 `${VAR}` 和 `$VAR`。
4. 检查引用的外部环境变量是否存在。
5. 只校验当前 flow 需要的字段。

例如：

```bash
run_de compile -d cpu_top
```

只校验：

```text
project
tools.vcs
flows.compile
```

不会因为 CDC、DC 或 FM 配置不完整而失败。

FM 是一个特例：`fm -time` 需要根据 `flows.syn.work_path` 找 DC 产物，因此加载 `fm` 时会额外保留并展开 `flows.syn` 的信息，但不会把 `syn` 当作当前执行 flow。

## Flow 注册

Flow 在 `deflow.flows.FLOW_SPECS` 中注册：

```python
FLOW_SPECS = {
    "compile": FlowSpec("compile"),
    "verdi": FlowSpec("verdi"),
    "lint": FlowSpec("tcl", ("-shell", "-tcl"), ("-tcl",)),
    "cdc": FlowSpec("tcl", ("-shell", "-tcl"), ("-tcl",)),
    "syn": FlowSpec("tcl", ("-f",)),
    "fm": FlowSpec("tcl", ("-f",)),
}
```

Flow 分为三类：

- 原生命令行：`compile`、`verdi`
- Tcl batch/shell：`lint`、`cdc`、`syn`、`fm`
- GUI/background：`verdi`，以及 SpyGlass `-gui`

## 运行策略

`deflow.runner` 提供几类进程启动方式：

### `run_process`

普通 pipe tee 模式：

- Python 接管 stdout/stderr。
- 实时打印到屏幕。
- 同时写入 `run.log`。
- 返回工具退出码。

当前用于：

- `compile`
- pexpect 不可用时的 fallback

### `run_pty_process`

伪终端模式：

- Linux 且安装 `pexpect` 时使用 pseudo-terminal。
- 工具行为更接近手工打开 shell。
- 输出写屏幕和 `run.log`。
- 如果当前 stdin 是 TTY，支持用户继续和工具交互。
- Windows 或缺少 `pexpect` 时 fallback 到 `run_process`。

当前用于：

- `lint`
- `cdc`
- `fm`

`requirements.txt` 中的 pexpect 依赖只在非 Windows 平台启用：

```text
pexpect>=4.9; sys_platform != "win32"
```

### `run_interactive_process`

真实终端直连模式：

- Python 不接管 stdout/stderr。
- 适合工具自己能写完整 log 的场景。

当前用于：

- `syn`

DC 使用：

```text
dc_shell -output_log_file <run_dir>/run.log -f syn.tcl
```

### `launch_process`

后台启动模式：

- 启动后立即返回。
- 用于 GUI 程序。

当前用于：

- `verdi`

## 运行目录

每次运行创建：

```text
<flow.work_path>/<design>_<flow>_<YYYYMMDD_HHMMSS>/
├── command.txt
├── resolved_config.yaml
├── run.log
├── run_context.tcl
├── reports/
└── outputs/
```

说明：

- 时间戳为秒级。
- `compile` 和 `verdi` 不生成 `run_context.tcl`。
- `resolved_config.yaml` 保存当前 flow 相关配置快照。
- `command.txt` 保存实际启动命令。
- `run.log` 保存工具输出；DC 由 `dc_shell -output_log_file` 生成，lint/cdc/fm 由 PTY tee 生成。

如果同一 design/flow 在同一秒重复启动，运行目录会冲突并报错。这是秒级时间戳的取舍。

## Context 数据协议

Python 生成 `run_context.tcl`，并通过环境变量传给 TCL：

```text
RUN_DE_CONTEXT=/path/to/run_context.tcl
```

TCL 统一调用：

```tcl
source [file join $script_dir .. common run_de_common.tcl]
run_de::load_context
```

`run_context.tcl` 是纯数据文件，例如：

```tcl
array set run_de {}

set run_de(flow) "fm"
set run_de(gui) "0"
set run_de(design) "cpu_top"
set run_de(work_dir) "/project/build/..."
set run_de(report_dir) "/project/build/.../reports"
set run_de(output_dir) "/project/build/.../outputs"
set run_de(sdc_file) "/project/constraints/cpu_top.sdc"
set run_de(impl_netlist) "/project/build/dc/.../outputs/cpu_top_syn.v"
set run_de(svf_file) "/project/build/dc/.../outputs/cpu_top_syn.svf"

set run_de(filelists) [list "/project/filelist/cpu_top.f" "/project/filelist/common.f"]
set run_de(defines) [list "TSMC_28HPC" "SYNTHESIS"]
set run_de(black_boxes) [list "memory"]
set run_de(library_files) [list "/pdk/db/stdcell.db"]
```

当前字段：

| 字段 | 说明 |
|---|---|
| `flow` | 当前 flow 名称 |
| `gui` | GUI 模式标志 |
| `design` | top module |
| `work_dir` | 本次运行目录 |
| `report_dir` | 报告目录 |
| `output_dir` | 输出目录 |
| `filelists` | RTL filelist 列表 |
| `defines` | 宏定义 |
| `black_boxes` | black-box 模块 |
| `library_files` | 当前工具使用的库文件 |
| `sdc_file` | 当前设计 SDC |
| `waiver_file` | SpyGlass waiver |
| `custom_policy_file` | SpyGlass custom policy |
| `constraint_post_tcl` | DC post-SDC hook |
| `dont_touch_tcl` | DC dont-touch hook |
| `dont_use_cell_tcl` | DC dont-use hook |
| `impl_netlist` | FM implementation netlist |
| `svf_file` | FM SVF |

Context 层不得包含 EDA 命令，例如：

```text
run_goal
compile_ultra
verify
write_report
```

这些必须保存在静态 TCL 中。

## 输入解析

### Filelist

主 filelist：

```text
<project.filelist_path>/<design>.f
```

公共 filelist：

- `project.common_file`
- `project.common_sim_file`

默认策略：

- `compile`、`verdi` 包含 common 和 common_sim。
- TCL flow 默认包含 common，不包含 common_sim。
- flow 可以通过 `include_common`、`include_sim` 覆盖。

### 库清单

由 `deflow.context._resolve_libraries()` 解析。

规则：

- SpyGlass 读取 `project.spyglass_lib_file`，只接受 `.lib` 和 `.lib.gz`。
- DC/Formality 读取 `project.common_db_file`，只接受 `.db`。
- 清单不存在则返回空列表。
- 清单存在但库文件不存在或扩展名错误则报错。

### SDC

SDC 路径：

```text
<project.sdc_path>/<design>.sdc
```

不存在时写入空字符串，由对应 TCL 决定如何处理。

### Formality DC 产物

`run_de fm -time <timestamp>` 使用：

```text
<flows.syn.work_path>/<design>_syn_<timestamp>/outputs/<design>_syn.v
<flows.syn.work_path>/<design>_syn_<timestamp>/outputs/<design>_syn.svf
```

Python 在启动 FM 前检查这两个文件是否存在，并写入：

```tcl
run_de(impl_netlist)
run_de(svf_file)
```

如果不传 `-time`，FM TCL 仍兼容旧的：

```text
RUN_DE_IMPL_NETLIST
```

## TCL 分层

### 公共 TCL

`tcl/common/run_de_common.tcl` 负责：

- 检查 `RUN_DE_CONTEXT`。
- source `run_context.tcl`。
- 检查必要字段。
- 提供 `run_de::optional_source`。
- 提供 SpyGlass batch 退出封装 `run_de::finish`。

该文件不放具体工具流程命令。

### SpyGlass

入口：

- `tcl/spyglass/lint.tcl`
- `tcl/spyglass/cdc.tcl`

公共实现：

- `tcl/spyglass/common.tcl`

公共流程：

1. `new_project`
2. 设置语言和公共选项。
3. CDC 时设置 SDC/clock 相关参数。
4. 读取 define、filelist、library。
5. 读取 SDC、black-box、methodology、policy、waiver。
6. 逐个执行 goal。
7. 每个 goal 后单独生成一套报告。
8. `save_project`。

`handle_large_bus` 只在 lint 中设置；CDC 不设置。

报告目录使用 goal 的最后一段，例如：

```text
lint/lint_rtl             -> reports/lint_rtl/
cdc/cdc_setup_check       -> reports/cdc_setup_check/
cdc/clock_reset_integrity -> reports/clock_reset_integrity/
```

### Design Compiler

入口：

```text
tcl/dc/syn.tcl
```

主要职责：

- 设置 SVF。
- 设置 host cores。
- 设置 bus naming。
- 设置 DesignWare synthetic library。
- 设置 target/link library。
- source dont-use hook。
- analyze/elaborate/link RTL。
- 写 GTECH 和 uniquified GTECH 快照。
- source SDC 和 post constraint hook。
- 执行 SDC sanity report。
- 执行 `compile_ultra`。
- 写 final reports。
- 写综合网表、DDC、SDC、SVF。

辅助报告：

- `tcl/dc/report_sdc_check.tcl`
- `tcl/dc/report_final.tcl`

### Formality

入口：

```text
tcl/formality/fm.tcl
```

主要职责：

- 设置 Formality 默认选项。
- 设置 command log。
- 读取 common DB。
- 读取 SVF。
- 使用 VCS 风格读取 reference RTL：

```tcl
read_sverilog -r -vcs "-f $filelist $fm_define_options -sverilog"
```

- 读取 implementation netlist。
- 对 reference 和 implementation 同时设置 black-box。
- `match`。
- 生成 match/unmatch 报告。
- `verify`。
- verify 失败时保存 `.fss` debug session。
- 生成 failing/unverified/status 等报告。

FM 默认复用 `flows.syn.defines`，保证 reference RTL 编译条件与 DC 综合一致。

## 扩展新 Flow

新增 flow 的推荐步骤：

1. 在 `tcl/<flow>/` 下创建静态 TCL 入口。
2. 在 `run_de_config.yaml` 中增加工具和 flow 配置。
3. 在 `deflow.config` 中增加该 flow 的字段校验。
4. 在 `deflow.cli` 中注册子命令。
5. 在 `deflow.flows.FLOW_SPECS` 中注册启动方式。
6. 如需新增 context 字段，在 `deflow.context` 中生成，并同步 TCL 使用端。
7. 增加 Python/TCL 测试。

新增 flow 时应避免：

- 新建独立 Python 入口脚本。
- 在 Python 中拼接 EDA TCL 命令。
- 用 `shell=True` 或 shell 字符串启动工具。
- 在多个 flow 中复制 filelist、runtime、log 逻辑。

## 测试策略

测试命令：

```bash
python -m unittest discover -s tests -v
```

覆盖内容：

- 配置加载和环境变量展开。
- 按当前 flow 校验配置。
- 设计名和 black-box 名校验。
- filelist 查找。
- 运行目录创建。
- context 数据生成。
- 工具命令参数。
- 进程 runner fallback。
- Tcl 文件语法完整性。
- 公共 Tcl 文件可被普通 Tcl interpreter source。
- 关键 Tcl 设置和报告逻辑存在性。

自动化测试不能替代真实 EDA smoke test。以下内容仍需在实际工具环境确认：

- SpyGlass methodology 和 goal 是否兼容当前版本。
- DC library、DesignWare、compile 选项是否符合项目需求。
- Formality SVF、reference/implementation 读取规则是否符合项目需求。
- GUI/交互行为是否符合团队使用方式。

## 维护约束

后续修改应遵循：

1. Python 只做调度和数据准备。
2. TCL 保存工具流程逻辑。
3. YAML 保存工程差异。
4. 每个新增配置字段都要有校验和测试。
5. 每个新增 context 字段都要同步检查所有使用端。
6. 每次运行必须保留命令、配置、context、log、reports、outputs。
7. 工具非零退出码必须向上返回。
8. 不为了局部便利破坏 Python/TCL/YAML 的职责边界。
