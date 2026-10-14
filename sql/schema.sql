-- Fichiers déjà traités (anti-doublons : un hash = un contenu unique)
CREATE TABLE IF NOT EXISTS processed_files (
    id              SERIAL PRIMARY KEY,
    file_name       TEXT      NOT NULL,
    file_hash       CHAR(64)  NOT NULL UNIQUE,
    nb_transactions INTEGER   NOT NULL,
    processed_at    TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Transactions détaillées avec leur flag
CREATE TABLE IF NOT EXISTS transactions (
    id                   SERIAL PRIMARY KEY,
    file_id              INTEGER       NOT NULL REFERENCES processed_files(id),
    datetime_transaction TIMESTAMP     NOT NULL,
    iban_origine         VARCHAR(34)   NOT NULL,
    pays_source          VARCHAR(100)  NOT NULL,
    banque_source        VARCHAR(100)  NOT NULL,
    iban_destinataire    VARCHAR(34)   NOT NULL,
    pays_destinataire    VARCHAR(100)  NOT NULL,
    montant              NUMERIC(15,2) NOT NULL CHECK (montant > 0),
    flag                 BOOLEAN       NOT NULL
);

-- Somme des montants envoyés par IBAN
CREATE TABLE IF NOT EXISTS sent_by_iban (
    iban  VARCHAR(34)   PRIMARY KEY,
    total NUMERIC(15,2) NOT NULL
);

-- Somme des montants envoyés par banque
CREATE TABLE IF NOT EXISTS sent_by_bank (
    banque VARCHAR(100)  PRIMARY KEY,
    total  NUMERIC(15,2) NOT NULL
);

-- Somme des montants reçus par IBAN
CREATE TABLE IF NOT EXISTS received_by_iban (
    iban  VARCHAR(34)   PRIMARY KEY,
    total NUMERIC(15,2) NOT NULL
);