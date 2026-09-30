CREATE TABLE IF NOT EXISTS users (
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	email TEXT,
	display_name TEXT,
	is_active BOOLEAN NOT NULL DEFAULT TRUE,
	email_verified_at TIMESTAMPTZ,
	created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT users_email_not_blank
		CHECK (email IS NULL OR btrim(email) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_unique_idx
	ON users (lower(email))
	WHERE email IS NOT NULL;

CREATE TABLE IF NOT EXISTS oauth_accounts (
	id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
	user_id UUID NOT NULL REFERENCES users (id) ON DELETE CASCADE,
	issuer TEXT NOT NULL,
	subject TEXT NOT NULL,
	created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
	CONSTRAINT oauth_accounts_issuer_not_blank CHECK (btrim(issuer) <> ''),
	CONSTRAINT oauth_accounts_subject_not_blank CHECK (btrim(subject) <> ''),
	CONSTRAINT oauth_accounts_issuer_subject_unique UNIQUE (issuer, subject)
);

CREATE INDEX IF NOT EXISTS oauth_accounts_user_id_idx
	ON oauth_accounts (user_id);
