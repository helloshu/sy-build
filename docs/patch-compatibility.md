# 上游补丁兼容性

`scripts/apply-patches.sh` 按文件名顺序应用 `patches/siyuan/*.patch`。每份补丁会收集精确标签覆盖、默认补丁、其他版本目录中的同名补丁作为候选。版本目录记录补丁适配的源码结构，不再限制该补丁只能用于对应版本。

脚本先检查所有候选是否已经应用，再依次尝试所有候选的完整上下文匹配，最后尝试至少保留一行上下文的匹配。完整匹配优先于宽松匹配。日志记录实际选用的补丁路径。候选必须通过 `git apply --check` 才会写入；所有候选都不兼容时立即失败，不跳过必需补丁，也不继续执行后续依赖补丁。此前已成功应用的补丁会保留在源码树中。

新增上游版本无需复制版本目录。只有源码变化导致现有候选全部失效时，才需要在 `patches/siyuan/versions/<上游标签>/` 添加更新后的同名补丁。未来版本也会自动尝试这个候选。各候选应实现相同功能；文本匹配不能证明接口、类型和运行行为兼容，仍需后续编译及功能验证。

工作流先执行 `check-patches`：运行补丁选择测试、对目标上游源码应用全部补丁、重复执行并比较差异、检查补丁后的空白错误和 Go 语法，并编译检查受影响的 Go 包（不执行测试用例）。通过后才启动桌面、Android、iOS、Docker 构建。不同平台继续使用同一脚本应用补丁。

定时构建继续追踪上游最新正式版。测试预发布版时，在手动运行工作流的 `version` 中填写完整标签，例如 `v3.8.7-alpha.1`。Android 优先使用同名标签；标签不存在时，仅在默认分支的 `siyuanVersionName` 与目标版本完全一致时使用该分支。预检查输出固定的提交 SHA，实际构建按该 SHA 检出，版本不匹配或网络请求失败时终止。`gomobile` 和 `gobind` 跟随上游 `go.mod` 中的 `golang.org/x/mobile` 版本，Android 使用与当前上游一致的 Java 21、NDK r28b 和 API 26。iOS 的营销版本只写入数字版本，例如 `3.8.7`，产物文件名保留完整预发布标签。补丁匹配和语法检查通过不代表各平台依赖、类型检查和运行行为必然兼容。

本地运行选择逻辑回归测试：

```sh
python3 -m unittest discover -s tests -v
```

在独立、干净的上游检出目录验证真实源码：

```sh
bash scripts/apply-patches.sh /path/to/siyuan
bash scripts/apply-patches.sh /path/to/siyuan
```

第二次应全部跳过，不产生新增差异。脚本保持兼容 macOS 自带 Bash 的数组语法，不使用关联数组、`mapfile` 或零上下文强制应用。

## v3.8.7 配置快照适配

`v3.8.7` 将 `AppConf.System`、`Sync`、`Repo` 等配置段改为原子指针，并重构了手动下载同步流程。`versions/v3.8.7/` 提供三份同名覆盖补丁：

- `disable-update.patch`：适配精简后的系统默认配置；使用 `LoadSystem()` 和会持久化的 `UpdateSystemConf()` 关闭安装包下载，避免直接修改已发布的配置快照。
- `sync-diagnostic.patch`：适配新的手动下载入口和同步配置快照，保留同步诊断、第三方同步无需官方账号的逻辑，以及订阅提醒的空用户保护。
- `zz-disable-official-services.patch`：适配 `SetSyncProvider(provider, completeAssets)`、同步和仓库配置读取、云服务声明及版本信息缓存结构，保留官方服务禁用逻辑。

同步诊断与官方服务补丁使用独立的小范围上下文，避免后者的插入使前者反向检查失败。默认补丁和 `v3.8.5` 覆盖保持原样，旧版继续按原有候选匹配。

2026-10-16 本地验证：15 项脚本回归测试通过；上游 `v3.8.7`（`7a7430d8a3cf362e23de004a454ddabe651dc778`）的 7 份补丁首次全部应用、再次全部跳过且差异不变；无精确标签时也能选中兼容候选。补丁后 `git diff --check`、Go 语法和格式检查通过，并在 Windows/amd64、Go 1.26.5、CGO 开启时执行 `go test -run '^$' -tags 'fts5 sqlcipher' ./api ./model ./mobile ./conf ./util`，五个包均通过编译检查；未执行各平台完整打包。

## v3.8.8 同步流程适配

`v3.8.8` 将 `autoSyncErrCount` 改为 `atomic.Int32`，自动同步失败过多的拦截移入 `notifyAutoSyncPaused()`，`syncData` 改为返回 `error`。三处改动使全部 `sync-diagnostic.patch` 候选在 `kernel/model/sync.go` 上失效，其余补丁仍能匹配现有候选（`disable-update` 与 `zz-disable-official-services` 继续选用 `v3.8.7` 版本）。

`versions/v3.8.8/sync-diagnostic.patch` 保留原有诊断日志、第三方同步免官方账号、订阅提醒空用户保护，调整如下：

- `syncModeGateLogged` 改为在 `syncProviderEndpointPresent()` 前单独声明，不再改写上游的 `var (...)` 块，降低以后变量块变化导致的失效风险。
- `syncData` 保持上游的命名返回值 `err`，诊断日志记录 `syncDataLocked` 的结果后原样返回；发生 panic 时仍保持上游的“sync did not complete”错误。
- 自动同步暂停日志改为在 `notifyAutoSyncPaused()` 返回 true 后记录 `autoSyncErrCount.Load()`，上游的提示和 64 分钟延迟逻辑不变。
- 补丁以 1 行上下文生成，避免与官方服务补丁的改动区域重叠，确保第二次运行时反向检查能识别已应用状态。

旧候选全部保留，`v3.8.5`、`v3.8.7` 仍分别选中原有补丁。

2026-10-23 本地验证：15 项脚本回归测试通过。上游 `v3.8.8`（`bfe36100477b7bbd66db1a8b8cff5547b2ccdb59`）、`v3.8.7`、`v3.8.5` 的 9 份补丁首次全部应用、再次全部跳过且差异不变，`git diff --check` 与 `gofmt` 通过；`v3.8.8`、`v3.8.7` 去掉标签后也能选中兼容候选。在 Linux/amd64、Go 1.26.5 下对补丁后的 `v3.8.8` 执行 `go test -run '^$' -tags 'fts5 sqlcipher' ./api ./model ./mobile ./conf ./util`，五个包均通过编译检查。上游 `model` 包的 `Sync|Exit` 测试中有 3 项失败，均为补丁有意改变的行为：默认同步服务改为 S3、无官方账号时允许第三方同步、官方云服务被禁用。未执行各平台完整打包。

## Docker 前端共享数据

`v3.8.7` 的 `app/src/protyle/render/av/lunarCalendar.ts` 从 `kernel/av/lunar_calendar_data.json` 导入农历数据。上游 Dockerfile 的 `node-build` 阶段只复制了 `app/`，即使 `go-build` 阶段已有 `kernel/`，前端编译仍会报模块不存在，因为两个阶段的文件系统相互独立。

`docker-build-assets.patch` 在前端构建阶段将 `kernel/av/` 复制到 `/kernel/av/`，保留该导入路径对应的目录结构。复制整个目录也兼容尚未引入农历 JSON 的旧版本。该补丁通过现有应用脚本自动应用，不需要修改各平台的构建命令。

验证：15 项脚本测试通过；`v3.8.7` 全部 8 份补丁应用成功，重复执行无新增差异，补丁后 `git diff --check` 通过；新补丁也在 `v3.8.5`、`v3.8.6` 的实际 Dockerfile 上通过应用和重复执行检查。按 `node-build` 的目录布局复现 JSON 模块缺失后，新增 COPY 可让相同的相对导入正确解析 1901–2100 年的数据。本机未安装 Docker，未执行完整镜像构建。

## Docker OCR 原生构建工具

`v3.8.7` 在 Alpine 中从源码构建 ONNX Runtime，CMake 使用 `patch` 命令修补 Eigen 等依赖。上游 Dockerfile 未安装该工具，导致 `Could NOT find Patch` 和 `Patch_EXECUTABLE-NOTFOUND`，在依赖配置阶段退出。

`docker-build-tools.patch` 在 `go-build` 阶段安装 Alpine 的 `patch` 包；`ocr-build` 从该阶段继承工具，最终运行镜像不包含新增的构建工具。该补丁也能用于尚未包含 OCR 阶段的旧版 Dockerfile。Docker 构建任务的时限调整为 90 分钟，为新增的 ONNX Runtime 原生编译保留时间。

实际编译还发现，固定提交的 ONNX Runtime 在 Release 构建中仍无条件包含 musl 未提供的 `execinfo.h`。`patches/onnxruntime/musl-release-stacktrace.patch` 让该头文件与已经受 `NDEBUG` 限制的回溯代码保持一致；Release 下本来就不生成回溯，因此不改变推理行为。Docker 任务仅在存在 `ocr-build` 阶段时应用 `patches/siyuan-docker/onnxruntime-musl.patch` 并复制原生补丁到构建上下文，在编译 ONNX Runtime 前执行；没有 OCR 阶段的旧版跳过此步骤。

上游的 `--skip_tests` 只跳过执行，仍默认编译单元测试和性能测试程序；其中性能测试程序在 GCC 15 上因缺少 `int64_t` 声明而失败。Docker 专用补丁设置 `onnxruntime_BUILD_UNIT_TESTS=OFF`，发布镜像只构建所需运行库及依赖，不构建这些测试程序。

2026-10-19 验证：15 项脚本测试通过；9 份通用补丁及 Docker 专用补丁的应用和重复执行检查通过，修改后的 Dockerfile 和 ONNX Runtime 源码空白检查通过。在失败日志对应的 Alpine 3.24.2 基础镜像中，使用同一 ONNX Runtime 提交完成依赖配置和 Release 共享库编译，并使用日志中的 Go 镜像工具链完成 OCR 辅助进程编译。另在仅安装最终镜像运行依赖的 Alpine 环境中，成功加载 ONNX Runtime 1.24.3、创建 API 23 环境，并确认辅助进程可以启动和处理 JSON 请求。未执行完整 Docker 镜像导出和实际 OCR 模型推理。
