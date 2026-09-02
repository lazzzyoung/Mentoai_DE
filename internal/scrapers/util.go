package scrapers

import (
	"context"
	"fmt"
	"log/slog"
	"math/rand"
	"time"
)

func nowRFC3339() string { return time.Now().UTC().Format(time.RFC3339Nano) }

func logf(format string, args ...any) { slog.Info(fmt.Sprintf(format, args...)) }

// sleepJitter는 ctx를 존중하며 base + [0, 0.3)초 대기한다 (예의 있는 크롤링).
func sleepJitter(ctx context.Context, r *rand.Rand, base float64) {
	timer := time.NewTimer(time.Duration((base + r.Float64()*0.3) * float64(time.Second)))
	defer timer.Stop()
	select {
	case <-ctx.Done():
	case <-timer.C:
	}
}
