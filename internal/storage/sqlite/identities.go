package sqlite

import (
	"context"
	"database/sql"
	"errors"
)

// Identities는 storage.IdentityRepo의 SQLite 구현이다.
type Identities struct {
	db *sql.DB
}

func (i *Identities) FindUserID(ctx context.Context, provider, providerUserID string) (*int64, error) {
	var userID int64
	err := i.db.QueryRowContext(ctx,
		"SELECT user_id FROM auth_identities WHERE provider = ? AND provider_user_id = ?",
		provider, providerUserID).Scan(&userID)
	if errors.Is(err, sql.ErrNoRows) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	return &userID, nil
}

func (i *Identities) Link(ctx context.Context, provider, providerUserID string, userID int64) error {
	_, err := i.db.ExecContext(ctx, `
		INSERT INTO auth_identities (provider, provider_user_id, user_id, created_at)
		VALUES (?, ?, ?, ?)
		ON CONFLICT (provider, provider_user_id) DO NOTHING`,
		provider, providerUserID, userID, Now())
	return err
}
