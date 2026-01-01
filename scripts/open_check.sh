#!/bin/bash
# macOS脚本：自动找到最近一次output目录并打开CHECK.html

# 默认搜索目录
SEARCH_DIRS=(
    "$HOME/OTBReview/output"
    "$HOME/OTBReview"
    "./out"
    "."
)

# 查找所有CHECK.html文件
CHECK_FILES=()

for dir in "${SEARCH_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        # 查找所有CHECK.html文件
        while IFS= read -r -d '' file; do
            CHECK_FILES+=("$file")
        done < <(find "$dir" -name "CHECK.html" -type f -print0 2>/dev/null)
    fi
done

# 如果没找到，尝试在当前目录的out/下查找
if [ ${#CHECK_FILES[@]} -eq 0 ]; then
    if [ -d "./out" ]; then
        while IFS= read -r -d '' file; do
            CHECK_FILES+=("$file")
        done < <(find "./out" -name "CHECK.html" -type f -print0 2>/dev/null)
    fi
fi

if [ ${#CHECK_FILES[@]} -eq 0 ]; then
    echo "❌ 未找到CHECK.html文件"
    echo ""
    echo "请先运行:"
    echo "  python scripts/make_check_report.py --outdir <输出目录>"
    exit 1
fi

# 按修改时间排序，取最新的
LATEST_CHECK=$(printf '%s\n' "${CHECK_FILES[@]}" | xargs -I{} sh -c 'echo "$(stat -f "%m %N" "{}" 2>/dev/null || stat -c "%Y %n" "{}" 2>/dev/null)"' | sort -rn | head -1 | cut -d' ' -f2-)

if [ -z "$LATEST_CHECK" ]; then
    echo "❌ 无法确定最新的CHECK.html"
    exit 1
fi

echo "📄 找到CHECK.html: $LATEST_CHECK"
echo "🚀 正在打开..."

# macOS使用open命令打开
if [[ "$OSTYPE" == "darwin"* ]]; then
    open "$LATEST_CHECK"
else
    # Linux使用xdg-open
    xdg-open "$LATEST_CHECK" 2>/dev/null || echo "请手动打开: $LATEST_CHECK"
fi

