import psycopg2
try:
    conn = psycopg2.connect("postgresql://pixi:pixipass@10.20.31.111:5433/pixi_test", connect_timeout=3)
    cur = conn.cursor()
    cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'module_test'")
    cols = cur.fetchall()
    print(cols)
except Exception as e:
    print(e)
