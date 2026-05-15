# wenyan-cli 主题列表

> 当前 forge / publisher 生产链路唯一保留的发布主题为 `sspai`（少数派）。
> 本文仅保留当前生产链路所需信息，避免 isolated session 被历史兼容说明误导。


wenyan-cli 支持多种内置主题，也支持自定义主题。

## 内置主题

查看所有内置主题：
```bash
wenyan theme -l
```

**当前生产主题：**

1. **sspai** - 少数派
   - 当前 forge / publisher 默认主题
   - 生产链路唯一保留主题

**完整主题列表：** https://github.com/caol64/wenyan-core/tree/main/src/assets/themes

## 代码高亮主题

### 亮色主题
- `atom-one-light` - Atom 编辑器亮色
- `github` - GitHub 风格
- `solarized-light` - Solarized 亮色（推荐）
- `xcode` - Xcode 默认

### 暗色主题
- `atom-one-dark` - Atom 编辑器暗色
- `dracula` - Dracula 主题
- `github-dark` - GitHub 暗色
- `monokai` - Monokai 经典
- `solarized-dark` - Solarized 暗色

## 自定义主题

### 临时使用
```bash
wenyan publish -f article.md -c /path/to/theme.css
```

### 永久安装
```bash
# 从本地文件
wenyan theme --add --name my-theme --path /path/to/theme.css

# 从网络
wenyan theme --add --name my-theme --path https://example.com/theme.css
```

### 使用已安装主题
```bash
wenyan publish -f article.md -t my-theme
```

### 删除主题
```bash
wenyan theme --rm my-theme
```

## 主题定制

如果你想创建自己的主题，可以参考：

1. **查看现有主题源码：** https://github.com/caol64/wenyan-core/tree/main/src/assets/themes
2. **CSS 变量参考：** wenyan 使用 CSS 变量定制样式
3. **测试主题：** 使用 `wenyan render` 命令仅渲染不发布

**示例：**
```bash
# 渲染测试（不发布）
wenyan render -f article.md -t my-theme -h github
```

## 推荐组合

### 技术文章
```bash
wenyan publish -f article.md -t sspai
```

### 当前生产风格
```bash
wenyan publish -f article.md -t sspai
```

## 更多选项

### 关闭 Mac 风格代码块
```bash
wenyan publish -f article.md -t sspai
```

### 关闭链接转脚注
```bash
wenyan publish -f article.md -t sspai
```

### 生产链路示例
```bash
wenyan publish -f article.md -t sspai
```
