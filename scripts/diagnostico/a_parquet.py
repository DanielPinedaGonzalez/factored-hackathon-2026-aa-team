# Diagnóstico: convierte cada tabla CSV a un Parquet (todo como texto, con el archivo de origen) una sola vez.
import duckdb, os, time

os.chdir(os.path.expanduser("~/Documentos/013Foundings/hackaton"))
os.makedirs("scratch/bronce", exist_ok=True)
c = duckdb.connect(config={"threads": 4, "memory_limit": "6GB"})

for t in ["customers", "products", "branches", "service_agents", "marketing_campaigns", "daily_exchange_rates"]:
    t0 = time.time()
    c.execute(f"copy (select *, '{t}.csv' as _archivo from read_csv('data/{t}.csv', all_varchar=true, header=true)) "
              f"to 'scratch/bronce/{t}.parquet' (format parquet)")
    print(t, round(time.time() - t0, 1), "s", flush=True)

for t in ["complaints", "call_center_interactions", "call_transcripts", "satisfaction_surveys",
          "transactions", "campaign_sends", "digital_events"]:
    t0 = time.time()
    c.execute(f"copy (select * from read_csv('data/{t}/**/*.csv', union_by_name=true, all_varchar=true, header=true, "
              f"filename='_archivo')) to 'scratch/bronce/{t}.parquet' (format parquet)")
    print(t, round(time.time() - t0, 1), "s", flush=True)
