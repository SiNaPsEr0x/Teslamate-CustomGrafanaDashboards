# TeslaMate Italiano + Custom Dashboards 🇮🇹

TeslaMate e Grafana in italiano, con Custom Grafana Dashboards integrate e aggiornamento automatico dai progetti upstream.

## Installazione: serve solo `compose.yml`

Per una nuova installazione **non servono `.env`, script, Dockerfile, clone del repository o configurazioni esterne**. Il solo file da usare è [`compose.yml`](compose.yml).

Avvio e aggiornamento usano sempre lo stesso comando:

```bash
docker compose -f compose.yml up -d --pull always
```

Il Compose scarica automaticamente tutte le immagini necessarie e avvia:

- TeslaMate
- Grafana con dashboard italiane e Custom Dashboards
- PostgreSQL
- Eclipse Mosquitto
- Traefik per l'accesso ai due servizi

TeslaMate e Grafana usano la **stessa unica immagine personalizzata**:

```text
ghcr.io/sinapser0x/teslamate:latest
```

## Password automatiche

Al primo avvio il Compose genera automaticamente password casuali forti e una chiave di cifratura. I valori vengono conservati nel volume Docker `sinapse-secrets` e **non vengono rigenerati agli aggiornamenti**.

Per visualizzare le due credenziali di accesso:

```bash
docker compose -f compose.yml logs bootstrap
```

L'output contiene:

```text
TeslaMate  -> user: teslamate  password: ...
Grafana    -> user: admin      password: ...
```

La password PostgreSQL e la chiave di cifratura TeslaMate vengono mantenute internamente e non sono stampate nei log.

> **Non eseguire `docker compose down -v` su un'installazione che contiene dati da conservare.** L'opzione `-v` elimina anche database, Grafana e segreti persistenti.

## Indirizzi

Dopo l'avvio:

- **TeslaMate:** `http://IP-DEL-SERVER:4000`
- **Grafana:** `http://IP-DEL-SERVER:3000`

TeslaMate è protetto da Basic Auth tramite Traefik. Grafana utilizza il proprio login amministratore.

La configurazione standalone usa HTTP per poter funzionare su qualsiasi NAS/server senza richiedere dominio, DNS o email Let's Encrypt. È pensata per rete locale, VPN o per essere posta dietro un reverse proxy HTTPS già esistente. **Non esporre direttamente le porte 3000/4000 su Internet senza TLS.**

## Portainer

In **Stacks → Add stack → Repository** usa:

| Campo | Valore |
|---|---|
| Repository URL | `https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git` |
| Repository reference | `refs/heads/main` |
| Compose path | `compose.yml` |

Non è necessario aggiungere Environment variables. Premi **Deploy the stack**.

In alternativa puoi copiare il contenuto del solo `compose.yml` nell'editor dello Stack.

## Aggiornamenti

Per aggiornare l'intero sistema riutilizza semplicemente:

```bash
docker compose -f compose.yml up -d --pull always
```

Docker scarica la versione più recente e ricrea solo i container necessari. I volumi persistenti restano invariati.

## Migrazione dalla precedente configurazione `.env`

Una nuova installazione non usa `.env`. Se invece stai migrando **un database TeslaMate già esistente** dalla precedente versione di questo progetto, il primo avvio deve conservare la vecchia `DATABASE_PASS` e soprattutto la vecchia `ENCRYPTION_KEY`.

Per compatibilità, il nuovo `compose.yml` può importare automaticamente una sola volta i vecchi valori `DATABASE_PASS`, `ENCRYPTION_KEY`, `BASIC_AUTH_PASSWORD` e `GRAFANA_ADMIN_PASSWORD` se sono ancora presenti nell'ambiente o nel vecchio `.env`. Dopo che il volume `sinapse-secrets` è stato creato e verificato, il vecchio `.env` non è più necessario.

Non collegare un vecchio database a una nuova chiave di cifratura.

## Architettura

```text
compose.yml
  │
  ├─ bootstrap     → genera e conserva i segreti al primo avvio
  ├─ database      → PostgreSQL ufficiale
  ├─ mosquitto     → Eclipse Mosquitto ufficiale
  ├─ proxy         → Traefik ufficiale
  │
  └─ ghcr.io/sinapser0x/teslamate:latest
        ├─ servizio Compose: teslamate
        └─ servizio Compose: grafana
```

Quindi il progetto ha **un repository, un file Compose e un solo pacchetto Docker personalizzato**. TeslaMate e Grafana restano processi/container separati per affidabilità, pur provenendo dalla stessa immagine.

## Aggiornamento automatico della distribuzione

GitHub Actions controlla automaticamente TeslaMate ufficiale e Custom Grafana Dashboards, applica le patch italiane, esegue i test applicativi, le migrazioni e i controlli sulle dashboard.

Solo dopo il superamento dei test viene pubblicata `ghcr.io/sinapser0x/teslamate:latest`. La pipeline esegue inoltre un'installazione pulita usando **esattamente il `compose.yml` pubblico senza `.env` e senza login GHCR**, verificando TeslaMate, Basic Auth, Grafana, datasource PostgreSQL e persistenza delle credenziali generate.

## Diagnostica

Stato dei container:

```bash
docker compose -f compose.yml ps
```

Log:

```bash
docker compose -f compose.yml logs --tail=200
```

Credenziali generate:

```bash
docker compose -f compose.yml logs bootstrap
```

## Crediti

Questa distribuzione non è una release ufficiale di TeslaMate o Custom Grafana Dashboards. Integra:

- [TeslaMate ufficiale](https://github.com/teslamate-org/teslamate)
- [Teslamate Custom Grafana Dashboards](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards)

Sono mantenute le rispettive licenze presenti nel repository.
