SELECT 'CREATE DATABASE dev'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'dev') \gexec

SELECT 'CREATE DATABASE staging'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'staging') \gexec

SELECT 'CREATE DATABASE prod'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'prod') \gexec

SELECT 'CREATE DATABASE test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'test') \gexec