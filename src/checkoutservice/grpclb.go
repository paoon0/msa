// gRPC のクライアント側負荷分散 (2026-10-06 追加)。
//
// 背景: 既定 (pick_first) では宛先ごとに接続を1本だけ張り、ClusterIP の Service 越しだと
// その1本が振り分けられた Pod に全呼び出しが行く (呼ばれる側の Pod に仕事が偏る)。
//
// 環境変数 GRPC_LB_POLICY=round_robin のときだけ有効 (未設定なら従来どおり = 過去の実験を再現できる):
//   - 宛先を DNS で引き、返ってきた全 Pod に接続を張って、呼び出しごとに順番に振り分ける。
//     宛先は headless Service (clusterIP: None) にしておく必要がある (DNS が Pod の IP を全部返す形)。
//   - GRPC_RESOLVE_EVERY 秒 (既定 30) ごとに DNS を引き直す。HPA が途中で足した Pod を見つけるため
//     (gRPC 標準の DNS リゾルバは、接続が切れたときにしか引き直さない)。
package main

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"sync"
	"time"

	"google.golang.org/grpc"
	"google.golang.org/grpc/resolver"
)

const pollScheme = "dnspoll"

// lbDialOptions は GRPC_LB_POLICY に応じて、宛先アドレスと追加の DialOption を返す。
func lbDialOptions(addr string) (string, []grpc.DialOption) {
	policy := os.Getenv("GRPC_LB_POLICY")
	if policy == "" || strings.HasPrefix(addr, "localhost:") || strings.HasPrefix(addr, "127.0.0.1:") {
		return addr, nil
	}
	every := 30 * time.Second
	if s := os.Getenv("GRPC_RESOLVE_EVERY"); s != "" {
		if n, err := strconv.Atoi(s); err == nil && n > 0 {
			every = time.Duration(n) * time.Second
		}
	}
	if i := strings.Index(addr, ":///"); i >= 0 {
		addr = addr[i+4:]
	}
	return pollScheme + ":///" + addr, []grpc.DialOption{
		grpc.WithResolvers(pollBuilder{inner: resolver.Get("dns"), every: every}),
		grpc.WithDefaultServiceConfig(fmt.Sprintf(`{"loadBalancingConfig":[{"%s":{}}]}`, policy)),
	}
}

// pollBuilder は標準の DNS リゾルバを包み、一定間隔で引き直しを促す。
type pollBuilder struct {
	inner resolver.Builder
	every time.Duration
}

func (b pollBuilder) Scheme() string { return pollScheme }

func (b pollBuilder) Build(t resolver.Target, cc resolver.ClientConn, o resolver.BuildOptions) (resolver.Resolver, error) {
	r, err := b.inner.Build(t, cc, o)
	if err != nil {
		return nil, err
	}
	p := &pollResolver{Resolver: r, done: make(chan struct{})}
	go func() {
		tk := time.NewTicker(b.every)
		defer tk.Stop()
		for {
			select {
			case <-tk.C:
				r.ResolveNow(resolver.ResolveNowOptions{})
			case <-p.done:
				return
			}
		}
	}()
	return p, nil
}

type pollResolver struct {
	resolver.Resolver
	done chan struct{}
	once sync.Once
}

func (p *pollResolver) Close() {
	p.once.Do(func() { close(p.done) })
	p.Resolver.Close()
}
