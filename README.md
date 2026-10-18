# SiNaPsE · TeslaMate Italiano + Custom Dashboards 🇮🇹

Distribuzione integrata di **TeslaMate**, dashboard Grafana ufficiali e **TeslaMate Custom Grafana Dashboards**, con le personalizzazioni italiane di SiNaPsEr0x.

**Un solo branch operativo e predefinito: `main`. Un solo workflow GitHub Actions.**

## Componenti e provenienza

| Componente | Sorgente | Personalizzazioni di questa versione |
|---|---|---|
| Applicazione TeslaMate | [teslamate-org/teslamate](https://github.com/teslamate-org/teslamate) | Catalogo italiano completo per la release, verifica dei plurali `msgstr[0]` e `msgstr[1]`, navigazione Grafana in base alla lingua |
| Dashboard ufficiali | `grafana/dashboards/` | Copie italiane con UID `-it`, titoli e campi visualizzati tradotti, SQL e variabili tecniche conservati |
| Custom Dashboards | [jheredianet/Teslamate-CustomGrafanaDashboards](https://github.com/jheredianet/Teslamate-CustomGrafanaDashboards), importato in `custom/` | 15 dashboard italiane iniziali, dizionario e validatore dedicati, nessuna riscrittura degli alias SQL, collegamento di ritorno a TeslaMate garantito nelle copie generate |
| Grafana | Dockerfile della release TeslaMate con integrazioni locali | Dashboard ufficiali inglesi/italiane e cartella **Custom TeslaMate · Italiano**, datasource con UID esplicito `TeslaMate` |
| Docker Compose | `compose.yml` nella radice | Build delle immagini dai sorgenti modificati, database PostgreSQL 18, MQTT, healthcheck, password richieste, dati persistenti |
| Aggiornamenti | Unico workflow `SiNaPsE · TeslaMate Italiano + Custom Dashboards` | Controllo di entrambi gli upstream, merge, validazione, test e pubblicazione transazionale su `main` |

La migrazione iniziale applica le sole patch linguistiche del fork `SiNaPsEr0x/teslamate` alla release stabile **v4.3.0**, evitando di importare il codice `4.4.0-dev` presente nel vecchio branch. La base iniziale Customs è **v2026.10.15**. Le versioni, gli SHA immutabili e gli ID delle release effettivamente verificati sono registrati in [`.github/unified-state.json`](.github/unified-state.json): questo file è il riferimento aggiornato dopo ogni sincronizzazione.

La cronologia dei due progetti e delle personalizzazioni è conservata. I branch storici rimossi sono recuperabili attraverso i tag `archive/2026-10-18/…`. Il vecchio `patch-1` modificava soglie di una dashboard BatteryHealth ormai sostituita upstream: è conservato nel tag archivio, senza ripristinare una dashboard obsoleta. Il vecchio fork separato `SiNaPsEr0x/teslamate` resta disponibile come archivio di provenienza; l'installazione integrata è questa repository.

## Installazione Docker in un unico comando

Richiede **Docker Engine**, **Docker Compose v2**, `git` e `openssl`, oltre all'accesso Internet e allo spazio necessario per database e build. Il comando seguente clona `main`, genera automaticamente tre credenziali casuali, crea `.env`, valida Compose, compila le immagini personalizzate, avvia l'intero stack e mostra lo stato finale.

```bash
git clone --depth 1 --branch main https://github.com/SiNaPsEr0x/Teslamate-CustomGrafanaDashboards.git && cd Teslamate-CustomGrafanaDashboards && printf 'ENCRYPTION_KEY=%s\nDATABASE_PASS=%s\nGRAFANA_ADMIN_PASSWORD=%s\nBIND_ADDRESS=127.0.0.1\nTESLAMATE_PORT=4000\nGRAFANA_PORT=3000\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 24)" "$(openssl rand -hex 24)" > .env && docker compose -f compose.yml config --quiet && docker compose -f compose.yml up -d --build && docker compose -f compose.yml ps
```

### Cosa crea

Compose costruisce direttamente dai sorgenti di questa repository due immagini locali: `sinapse/teslamate:local` con TeslaMate e le patch italiane, e `sinapse/teslamate-grafana:local` con Grafana, dashboard ufficiali italiane e Custom Dashboards italiane. Avvia inoltre PostgreSQL 18 e Mosquitto. Il database deve diventare `healthy` prima dell'avvio dei servizi che ne dipendono.

Le credenziali generate restano esclusivamente nel file locale `.env`, che è escluso da Git. Per recuperare la password amministratore Grafana dopo l'installazione usa `grep GRAFANA_ADMIN_PASSWORD .env`. Non rigenerare `ENCRYPTION_KEY` su un'installazione esistente: TeslaMate la usa per i dati cifrati.

Accesso locale predefinito: TeslaMate `http://127.0.0.1:4000`, Grafana `http://127.0.0.1:3000` con utente `admin`. Il bind su `127.0.0.1` evita di pubblicare automaticamente i servizi sulla LAN. Se il server deve essere raggiungibile da altri dispositivi, modifica consapevolmente `BIND_ADDRESS` in `.env` e ricrea i container.

In TeslaMate seleziona **Italiano** nelle impostazioni della lingua per usare anche i collegamenti alle dashboard ufficiali italiane. Le Custom Dashboards italiane sono già integrate nell'immagine Grafana, senza download o bind mount manuali. Il datasource configurato nell'immagine ha nome e UID `TeslaMate`. Non aggiungere un secondo datasource con lo stesso nome.

I dati persistono nei volumi `teslamate-db`, `teslamate-grafana`, `mosquitto-conf` e `mosquitto-data`. Il database non espone la porta PostgreSQL sull'host; MQTT resta nella rete Compose.

## Aggiornare una propria installazione

Il workflow aggiorna e verifica il repository. **Non si collega al tuo server e non aggiorna automaticamente i container installati.**

Prima di aggiornare un'installazione esistente, conserva backup del database, `.env`, versione/commit installato e dati Grafana. Un downgrade dei container non annulla le migrazioni PostgreSQL: per un rollback con schema incompatibile serve il backup precedente.

```bash
cd Teslamate-CustomGrafanaDashboards
git pull --ff-only origin main
docker compose -f compose.yml config --quiet
docker compose -f compose.yml up -d --build
docker compose -f compose.yml ps
docker compose -f compose.yml logs --tail=100 teslamate grafana
```

**Migrazione da un Compose precedente:** non collegare alla cieca i vecchi volumi. Nomi/progetto Compose, credenziali, chiave di cifratura e UID datasource devono corrispondere all'installazione. PostgreSQL 18 usa il volume montato su `/var/lib/postgresql`, con sottocartella della versione; un volume PostgreSQL precedente montato su `/var/lib/postgresql/data` richiede una migrazione esplicita. Cambiare soltanto il percorso può far apparire un database vuoto. Anche i riferimenti ad altri UID datasource già usati da dashboard personali vanno verificati prima di sostituire il provisioning.

## Unica automazione

Il workflow parte su push a `main`, manualmente e ogni giorno alle **06:23 UTC**; GitHub può ritardare le esecuzioni pianificate e può disabilitarle dopo 60 giorni di inattività del repository.

1. Risolve l'ultima release stabile pubblicata di entrambi gli upstream e verifica SHA e tag precedenti.
2. Prepara un candidato in un worktree temporaneo: merge normale per TeslaMate, merge con prefisso `custom/` per Customs. Le patch italiane restano nella cronologia locale.
3. Conserva traduzioni e infrastruttura della distribuzione; rigenera dashboard ufficiali e custom italiane. I workflow upstream importati non sono attivi: rimane un solo YAML in `.github/workflows/`.
4. Esegue controlli dei cataloghi, test Python, build dei due Dockerfile, suite Elixir inclusi test linguistici/plurali, validazione Compose, migrazioni su database temporaneo, preparazione e pianificazione SQL delle dashboard custom, avvio HTTP dell'applicazione e provisioning/API/healthcheck Grafana.
5. Pubblica su `main` soltanto dopo i controlli, con push ordinario. Non esegue rebase né force-push; un aggiornamento concorrente blocca la pubblicazione.

Errori, conflitti, tag spostati, traduzioni mancanti e incompatibilità generano una Issue dettagliata e lasciano il candidato non pubblicato. Nuove frasi non sono tradotte automaticamente per supposizione: la Issue elenca le voci da aggiungere ai dizionari. Una nuova release TeslaMate produce anche una Issue di revisione con il diff, perché i test automatici non coprono ogni combinazione di dati o interazione del browser.

Gli artefatti `sinapse-teslamate-RUN_ID` contengono dashboard generate, report, log di build/test/migrazioni/SQL/Grafana e diff degli upstream. Durata: 30 giorni. Le esecuzioni senza nuove release ripetono le verifiche e non creano commit quando lo stato è invariato. L'upload degli artefatti usa l'azione corrente basata sul runtime Node 24.

## Struttura e licenze

- Radice, `elixir/`, `grafana/`, `rust/`: sorgenti TeslaMate e patch locali.
- `custom/`: progetto Customs completo, incluse traduzioni e documentazione originale.
- `config/grafana/`: provisioning integrato.
- `tools/`: importazione, sincronizzazione, validazione e test della distribuzione.
- `docs/TESLAMATE-UPSTREAM.md`: README TeslaMate originale al momento dell'importazione.

TeslaMate mantiene la sua licenza **AGPL-3.0-or-later**, con `LICENSE` e `NOTICE` nella radice. Customs mantiene la propria licenza in `custom/LICENSE`. Questa distribuzione conserva i sorgenti e le attribuzioni dei rispettivi autori; non è una release ufficiale dei due progetti.

## Protezione del branch e autenticazione dell'automazione

L'aggiornamento usa la chiave deploy dedicata **SiNaPsE unified automatic updates**, limitata a questa repository. La parte privata è custodita nel Secret Actions `SINAPSE_UNIFIED_SYNC_SSH_KEY`; non è contenuta nei sorgenti o negli artefatti. Il token temporaneo `GITHUB_TOKEN` serve per interrogare le release e gestire le Issue.

Due ruleset proteggono `main`: uno vieta force-push e cancellazione senza eccezioni; l'altro mantiene revisione, approvazione dell'ultimo push e firme per i contributi ordinari, con bypass per amministratori e chiavi deploy. La chiave dedicata consente al workflow di pubblicare dopo le proprie verifiche senza richiedere ogni volta una PR. I push dell'automazione non avviano nuovamente il workflow.

La precedente sincronizzazione generica del bot Pull è disabilitata con `.github/pull.yml`: il controllo dei due upstream è gestito dall'unico workflow della distribuzione.
