package runner

import (
	"context"
	"encoding/json"

	"github.com/redis/go-redis/v9"
)

type Dispatcher struct {
	rdb *redis.Client
}

func NewDispatcher(rdb *redis.Client) *Dispatcher {
	return &Dispatcher{rdb: rdb}
}

func (d *Dispatcher) Publish(ctx context.Context, language string, msg *JobMessage) error {
	payload, err := json.Marshal(msg)
	if err != nil {
		return err
	}
	return d.rdb.LPush(ctx, QueueName(language), payload).Err()
}
