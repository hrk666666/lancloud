#!/usr/bin/env bash
# LanCloud 功能自测脚本
# 用法：bash test_api.sh            （默认 8080）
#       BASE=http://127.0.0.1:18080 bash test_api.sh   （自定义端口）
set -e
BASE="${BASE:-http://127.0.0.1:8080}"
JAR=/tmp/lc_cookie.txt
rm -f $JAR
PASS=0; FAIL=0

enc() { python3 -c "import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1]))" "$1"; }

ok() { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

check() {
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (期望 $2 实际 $3)"; fi
}

echo "== 1. 登录 =="
R=$(curl -s -c $JAR -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}')
echo "$R" | grep -q '"ok":true' && ok "admin 登录" || bad "admin 登录: $R"

echo "== 2. 当前用户 =="
R=$(curl -s -b $JAR $BASE/api/auth/me)
echo "$R" | grep -q '"is_admin":true' && ok "me 返回管理员" || bad "me: $R"

echo "== 3. 新建文件夹 =="
R=$(curl -s -b $JAR -X POST $BASE/api/fs/mkdir -H 'Content-Type: application/json' -d '{"path":"","name":"测试目录"}')
echo "$R" | grep -q '"ok":true' && ok "mkdir" || bad "mkdir: $R"

echo "== 4. 上传文件 =="
echo "LanCloud 测试文件内容 hello" > /tmp/test.txt
R=$(curl -s -b $JAR -X POST "$BASE/api/fs/upload?path=$(enc "测试目录")" -F "files=@/tmp/test.txt")
echo "$R" | grep -q '"ok":true' && ok "upload" || bad "upload: $R"

echo "== 5. 目录列表 =="
R=$(curl -s -b $JAR "$BASE/api/fs/list?path=$(enc "测试目录")")
echo "$R" | grep -q '"test.txt"' && ok "list 包含 test.txt" || bad "list: $R"

echo "== 6. 重命名 =="
R=$(curl -s -b $JAR -X POST $BASE/api/fs/rename -H 'Content-Type: application/json' -d '{"path":"测试目录/test.txt","new_name":"改名.txt"}')
echo "$R" | grep -q '"ok":true' && ok "rename" || bad "rename: $R"

echo "== 7. 移动 =="
curl -s -b $JAR -X POST $BASE/api/fs/mkdir -H 'Content-Type: application/json' -d '{"path":"","name":"目标目录"}' > /dev/null
R=$(curl -s -b $JAR -X POST $BASE/api/fs/move -H 'Content-Type: application/json' -d '{"path":"测试目录/改名.txt","dest":"目标目录"}')
echo "$R" | grep -q '"ok":true' && ok "move" || bad "move: $R"

echo "== 8. 下载（含 Range） =="
CODE=$(curl -s -o /tmp/dl.txt -w "%{http_code}" -b $JAR "$BASE/api/fs/download?path=$(enc "目标目录/改名.txt")")
[ "$CODE" = "200" ] && ok "download 200" || bad "download $CODE"
R=$(curl -s -o /dev/null -w "%{http_code}" -b $JAR -H "Range: bytes=0-4" "$BASE/api/fs/download?path=$(enc "目标目录/改名.txt")")
[ "$R" = "206" ] && ok "Range 请求 206" || bad "Range: $R"

echo "== 9. 搜索 =="
R=$(curl -s -b $JAR "$BASE/api/fs/search?q=$(enc "改名")")
echo "$R" | grep -q '改名.txt' && ok "search" || bad "search: $R"

echo "== 10. 分享 =="
R=$(curl -s -b $JAR -X POST $BASE/api/share -H 'Content-Type: application/json' -d '{"path":"目标目录/改名.txt"}')
TOKEN=$(echo "$R" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
[ -n "$TOKEN" ] && ok "share token=$TOKEN" || bad "share: $R"
R=$(curl -s "$BASE/api/s/$TOKEN/info")
echo "$R" | grep -q '改名.txt' && ok "分享公开访问 info" || bad "share info: $R"
CODE=$(curl -s -o /tmp/sdl.txt -w "%{http_code}" "$BASE/api/s/$TOKEN/download")
[ "$CODE" = "200" ] && ok "分享下载 200" || bad "分享下载 $CODE"

echo "== 11. 回收站 =="
curl -s -b $JAR -X POST $BASE/api/fs/delete -H 'Content-Type: application/json' -d '{"path":"目标目录/改名.txt"}' > /dev/null
R=$(curl -s -b $JAR $BASE/api/trash)
echo "$R" | grep -q '改名.txt' && ok "删除后进入回收站" || bad "trash: $R"
curl -s -b $JAR -X POST $BASE/api/trash/restore -H 'Content-Type: application/json' -d '{"trash_name":"改名.txt"}' > /dev/null
R=$(curl -s -b $JAR "$BASE/api/fs/list?path=$(enc "目标目录")")
echo "$R" | grep -q '改名.txt' && ok "恢复成功" || bad "restore: $R"

echo "== 12. 管理概览 =="
R=$(curl -s -b $JAR $BASE/api/admin/overview)
echo "$R" | grep -q '"dns"' && ok "overview 返回" || bad "overview: $R"

echo "== 13. 域名映射 CRUD =="
R=$(curl -s -b $JAR -X POST $BASE/api/dns/domains -H 'Content-Type: application/json' -d '{"domain":"pan.lan","ip":"192.168.1.100","note":"测试"}')
echo "$R" | grep -q '"ok":true' && ok "添加域名映射" || bad "add domain: $R"
DID=$(echo "$R" | sed -n 's/.*"id":"\([^"]*\)".*/\1/p' | head -1)
R=$(curl -s -b $JAR -X PUT "$BASE/api/dns/domains/$DID" -H 'Content-Type: application/json' -d '{"enabled":false}')
echo "$R" | grep -q '"ok":true' && ok "停用映射" || bad "disable: $R"
R=$(curl -s -b $JAR -X DELETE "$BASE/api/dns/domains/$DID")
echo "$R" | grep -q '"ok":true' && ok "删除映射" || bad "delete: $R"

echo "== 14. 未登录访问被拒绝 =="
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/fs/list?path=")
[ "$CODE" = "401" ] && ok "未登录 401" || bad "未登录返回 $CODE"

echo ""
echo "结果：通过 $PASS 项，失败 $FAIL 项"
[ "$FAIL" = "0" ]
