#!/usr/bin/env bash
# LanCloud v2 API 集成测试
BASE="${BASE:-http://127.0.0.1:18081}"
JAR=$(mktemp)
PASS=0; FAIL=0
say() { echo "$1"; }
ok() { PASS=$((PASS+1)); say "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); say "  ✗ $1"; }
check() { # check 描述 期望 实际
  if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (期望=$2 实际=$3)"; fi
}
jqget() { # jqget 文件 完整表达式(如 d['is_admin'] 或 len(d['items']))
  .venv/bin/python -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1" 2>/dev/null
}

echo "== 0. 清理上次测试数据（保证幂等） =="
curl -s -c $JAR -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' > /tmp/t.json
for u in alice bob carol; do curl -s -b $JAR -X DELETE $BASE/api/admin/users/$u > /dev/null; done
IDS=$(curl -s -b $JAR $BASE/api/dns/domains | .venv/bin/python -c "import json,sys; print(' '.join(d['id'] for d in json.load(sys.stdin)['items']))")
for id in $IDS; do curl -s -b $JAR -X DELETE $BASE/api/dns/domains/$id > /dev/null; done
for m in $(curl -s -b $JAR $BASE/api/mounts | .venv/bin/python -c "import json,sys; print(' '.join(x['id'] for x in json.load(sys.stdin)['items']))"); do curl -s -b $JAR -X DELETE $BASE/api/mounts/$m > /dev/null; done

echo "== 1. 登录与基本信息 =="
curl -s -c $JAR -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' > /tmp/t.json
check "admin 登录" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR $BASE/api/auth/me > /tmp/t.json
check "me 返回管理员" 'True' "$(jqget /tmp/t.json "d['is_admin']")"
check "me 返回默认配额0" '0' "$(jqget /tmp/t.json "d['quota_mb']")"
check "me 返回可分享" 'True' "$(jqget /tmp/t.json "d['can_share']")"

echo "== 2. 用户管理 =="
curl -s -b $JAR -X POST $BASE/api/admin/users -H 'Content-Type: application/json' -d '{"username":"alice","password":"pass123","quota_mb":5}' > /tmp/t.json
check "创建 alice" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR -X POST $BASE/api/admin/users/batch -H 'Content-Type: application/json' -d '{"lines":"bob pass456 10\ncarol pass789"}' > /tmp/t.json
check "批量创建2个成功" '2' "$(jqget /tmp/t.json "len([r for r in d['results'] if r['ok']])")"
curl -s -b $JAR $BASE/api/admin/users > /tmp/t.json
check "用户列表含4人" '4' "$(jqget /tmp/t.json "len(d['items'])")"
curl -s -b $JAR -X PUT $BASE/api/admin/users/alice -H 'Content-Type: application/json' -d '{"quota_mb":20,"disabled":true}' > /tmp/t.json
check "更新 alice 配额与禁用" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR -X POST $BASE/api/admin/users/alice/reset-password -H 'Content-Type: application/json' -d '{"password":"newpass1"}' > /tmp/t.json
check "重置密码" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"alice","password":"newpass1"}')
check "禁用后 alice 无法登录 401" '401' "$code"
curl -s -b $JAR -X PUT $BASE/api/admin/users/alice -H 'Content-Type: application/json' -d '{"disabled":false}' > /tmp/t.json
JAR2=$(mktemp)
curl -s -c $JAR2 -X POST $BASE/api/auth/login -H 'Content-Type: application/json' -d '{"username":"alice","password":"newpass1"}' > /tmp/t.json
check "重新启用后可登录" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"

echo "== 3. 配额上传限制 =="
curl -s -b $JAR -X PUT $BASE/api/admin/users/alice -H 'Content-Type: application/json' -d '{"quota_mb":5}' > /tmp/t.json
echo "hello world" > /tmp/small.txt
curl -s -b $JAR2 -X POST "$BASE/api/fs/upload?path=" -F "files=@/tmp/small.txt" > /tmp/t.json
check "alice 上传小文件成功" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
head -c 6M /dev/zero > /tmp/big.bin
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -b $JAR2 -X POST "$BASE/api/fs/upload?path=" -F "files=@/tmp/big.bin")
check "alice 超配额(5MB)被拒 413" '413' "$code"

echo "== 4. 分享增强 =="
curl -s -b $JAR2 -X POST $BASE/api/share -H 'Content-Type: application/json' -d '{"path":"small.txt","require_login":true,"expire_days":1}' > /tmp/t.json
TOK=$(jqget /tmp/t.json "d['token']")
check "创建强制登录分享" 'True' "$(jqget /tmp/t.json "d['require_login']")"
code=$(curl -s -o /tmp/t.json -w '%{http_code}' $BASE/api/s/$TOK/info)
check "未登录访问被拒 401" '401' "$code"
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -b $JAR2 $BASE/api/s/$TOK/info)
check "登录后访问成功 200" '200' "$code"
curl -s -b $JAR2 -X POST $BASE/api/share -H 'Content-Type: application/json' -d '{"path":"small.txt","require_login":false,"expire_days":0}' > /tmp/t.json
TOK2=$(jqget /tmp/t.json "d['token']")
code=$(curl -s -o /tmp/t.json -w '%{http_code}' $BASE/api/s/$TOK2/info)
check "免登录分享公开可访问 200" '200' "$code"
curl -s -b $JAR -X PUT $BASE/api/admin/users/alice -H 'Content-Type: application/json' -d '{"can_share":false}' > /tmp/t.json
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -b $JAR2 -X POST $BASE/api/share -H 'Content-Type: application/json' -d '{"path":"small.txt"}')
check "禁止分享后创建被拒 403" '403' "$code"

echo "== 5. 外部文件夹挂载 =="
mkdir -p /tmp/mountlib/sub
echo "mount file" > /tmp/mountlib/a.txt
echo "sub file" > /tmp/mountlib/sub/b.txt
curl -s -b $JAR -X POST $BASE/api/mounts -H 'Content-Type: application/json' -d '{"name":"测试共享","path":"/tmp/mountlib","readonly":true}' > /tmp/t.json
MID=$(jqget /tmp/t.json "d['mount']['id']")
check "添加挂载" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR2 $BASE/api/mounts > /tmp/t.json
check "普通用户可见挂载" '1' "$(jqget /tmp/t.json "len(d['items'])")"
curl -s -b $JAR2 "$BASE/api/mounts/$MID/browse?path=" > /tmp/t.json
check "浏览挂载根目录" 'True' "$(jqget /tmp/t.json "\"a.txt\" in [i['name'] for i in d['items']]")"
curl -s -b $JAR2 "$BASE/api/mounts/$MID/browse?path=sub" > /tmp/t.json
check "浏览子目录" 'b.txt' "$(jqget /tmp/t.json "d['items'][0]['name']")"
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -b $JAR2 "$BASE/api/mounts/$MID/download?path=a.txt")
check "挂载文件下载 200" '200' "$code"
code=$(curl -s -o /dev/null -w '%{http_code}' -b $JAR2 "$BASE/api/mounts/$MID/download?path=../../etc/passwd")
check "路径穿越被拒 400" '400' "$code"

echo "== 6. 在线编辑与 zip =="
curl -s -b $JAR2 -X PUT $BASE/api/fs/edit -H 'Content-Type: application/json' -d '{"path":"small.txt","content":"edited content"}' > /tmp/t.json
check "文本编辑保存" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR2 "$BASE/api/fs/read?path=small.txt" > /tmp/t.json
check "读取已编辑内容" 'edited content' "$(jqget /tmp/t.json "d['content']")"
curl -s -b $JAR2 -X POST $BASE/api/fs/mkdir -H 'Content-Type: application/json' -d '{"path":"","name":"zipdir"}' > /tmp/t.json
curl -s -b $JAR2 -X POST "$BASE/api/fs/upload?path=zipdir" -F "files=@/tmp/small.txt" > /tmp/t.json
code=$(curl -s -o /tmp/zip.bin -w '%{http_code}' -b $JAR2 "$BASE/api/fs/zip?path=zipdir")
check "目录打包下载 200" '200' "$code"
file /tmp/zip.bin | grep -q "Zip archive" && ok "zip 文件有效" || bad "zip 文件无效"
code=$(curl -s -o /tmp/zip2.bin -w '%{http_code}' -b $JAR2 "$BASE/api/fs/zip?path=small.txt")
check "单文件打包 200" '200' "$code"

echo "== 7. DNS 与诊断 =="
curl -s -b $JAR -X POST $BASE/api/dns/domains -H 'Content-Type: application/json' -d '{"domain":"pan.lan","ip":"127.0.0.1","note":"测试"}' > /tmp/t.json
check "添加域名映射" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
curl -s -b $JAR $BASE/api/diag > /tmp/t.json
check "诊断 DNS 自测通过" 'True' "$(jqget /tmp/t.json "d['self_tests'][0]['ok']")"
curl -s -b $JAR $BASE/api/dns/log > /tmp/t.json
check "DNS 查询日志非空" 'True' "$(jqget /tmp/t.json "len(d['items'])>0")"

echo "== 8. HTTPS 与配置 =="
curl -s -b $JAR $BASE/api/https/status > /tmp/t.json
check "HTTPS 状态接口" 'False' "$(jqget /tmp/t.json "d['enabled']")"
curl -s -b $JAR -X PUT $BASE/api/admin/config -H 'Content-Type: application/json' -d '{"allow_register":false,"default_quota_mb":100}' > /tmp/t.json
check "修改全局配置" '"ok":true' "$(grep -o '"ok":true' /tmp/t.json)"
code=$(curl -s -o /tmp/t.json -w '%{http_code}' -X POST $BASE/api/auth/register -H 'Content-Type: application/json' -d '{"username":"nobody","password":"pass123"}')
check "关闭注册后注册被拒 403" '403' "$code"
code=$(curl -s -o /tmp/ca.crt -w '%{http_code}' -b $JAR $BASE/api/ca/download)
check "CA 证书下载 200" '200' "$code"
grep -q "BEGIN CERTIFICATE" /tmp/ca.crt && ok "CA 证书有效" || bad "CA 证书无效"

echo ""
echo "结果: 通过 $PASS 项, 失败 $FAIL 项"
exit $FAIL
