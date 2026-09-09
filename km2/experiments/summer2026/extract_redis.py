#!/usr/bin/env python3
"""cartservice.yaml から redis-cart の定義だけを取り出す。

なぜ要るか: 4つ束ね(frontrecocartcatalog)では cartservice を frontend Pod に同居させるので
  cartservice の Deployment / Service / ServiceAccount は不要。しかし redis-cart は
  状態を持つため束ねの外に残す必要があり、同じファイルに同居している。

注意: 「文字列 redis-cart を含むか」で絞ってはいけない。cartservice の Deployment は
  REDIS_ADDR: "redis-cart:6379" を持つため一致してしまう(2026-09-03 に実際に踏んだ)。
  metadata.name で判定する。
"""
import sys, re

docs = open(sys.argv[1]).read().split('\n---\n')
keep = []
for d in docs:
    m = re.search(r'^metadata:\n(?:\s+.*\n)*?\s+name:\s*(\S+)', d, re.M)
    if m and m.group(1) == 'redis-cart':
        keep.append(d.strip('\n'))
print('\n---\n'.join(keep))
