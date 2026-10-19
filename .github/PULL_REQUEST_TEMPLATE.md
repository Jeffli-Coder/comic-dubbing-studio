## 改动内容

<!-- 一句话说明这个 PR 做了什么 -->

## 动机 / 关联 Issue

Closes #

## 验证方式

- [ ] `pytest -q` 通过
- [ ] `ruff check .` 通过
- [ ] 已在 `MOCK_MODE=1` 下手动验证上传 → 播放 → 换音色
- [ ] 涉及 Docker/依赖时：`docker build` 与容器 smoke test 通过

## 检查清单

- [ ] 没有提交 `.env`、密钥、漫画/音频等版权素材或本地 `data/`
- [ ] 新增外部服务调用走 `providers/` 抽象，并处理缺 Key 降级
- [ ] 新增行为有对应测试
- [ ] 更新了相关文档（README / docs/）