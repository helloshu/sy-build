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
