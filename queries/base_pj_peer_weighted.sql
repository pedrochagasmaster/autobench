WITH base_data AS (
    SELECT
        *,
        CASE
            WHEN issuer_name IN (
                'BANCO BTG PACTUAL SA',
                'BANCO C6 SA',
                'BANCO INTER S.A.',
                'CLARA PAGAMENTOS SA',
                'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG',
                'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME'
            ) THEN 'digital' ELSE 'incumbent' 
        END AS peer_group
    FROM
        coe_enc.e176097_nubank_pj_peer_cube
),

-- Per-dimension weights for credit_debit_flag
weighted_credit_debit AS (
    SELECT
        peer_group,
        month_year_num AS ano_mes,
        credit_debit_flag,
        CASE
            -- Digital peers
            WHEN issuer_name = 'BANCO BTG PACTUAL SA' THEN 3.565423
            WHEN issuer_name = 'BANCO C6 SA' THEN 0.148327
            WHEN issuer_name = 'BANCO INTER S.A.' THEN 0.183723
            WHEN issuer_name = 'CLARA PAGAMENTOS SA' THEN 0.311827
            WHEN issuer_name = 'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG' THEN 1.650239
            WHEN issuer_name = 'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME' THEN 0.140461
            -- Incumbent peers
            WHEN issuer_name = 'BANCO BRADESCO S.A.' THEN 4.620438
            WHEN issuer_name = 'BANCO COOPERATIVO SICOOB S.A. - BANCO SI' THEN 0.06846
            WHEN issuer_name = 'BANCO SANTANDER (BRASIL) S.A.' THEN 0.057312
            WHEN issuer_name = 'CAIXA ECONOMICA FEDERAL' THEN 0.240584
            WHEN issuer_name = 'ITAU UNIBANCO S.A.' THEN 0.013206
            ELSE 1.0
        END AS peer_weight,
        SUM(1) AS txn_cnt,
        SUM(amt_local_currency) AS tpv
    FROM base_data
    GROUP BY peer_group, month_year_num, credit_debit_flag, issuer_name
),

-- Per-dimension weights for tipo_compra
weighted_tipo_compra AS (
    SELECT
        peer_group,
        month_year_num AS ano_mes,
        tipo_compra,
        CASE
            -- Digital peers
            WHEN issuer_name = 'BANCO BTG PACTUAL SA' THEN 2.281259
            WHEN issuer_name = 'BANCO C6 SA' THEN 0.163481
            WHEN issuer_name = 'BANCO INTER S.A.' THEN 0.12622
            WHEN issuer_name = 'CLARA PAGAMENTOS SA' THEN 0.594178
            WHEN issuer_name = 'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG' THEN 2.490163
            WHEN issuer_name = 'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME' THEN 0.3447
            -- Incumbent peers
            WHEN issuer_name = 'BANCO BRADESCO S.A.' THEN 4.176589
            WHEN issuer_name = 'BANCO COOPERATIVO SICOOB S.A. - BANCO SI' THEN 0.054825
            WHEN issuer_name = 'BANCO SANTANDER (BRASIL) S.A.' THEN 0.050756
            WHEN issuer_name = 'CAIXA ECONOMICA FEDERAL' THEN 0.677047
            WHEN issuer_name = 'ITAU UNIBANCO S.A.' THEN 0.040784
            ELSE 1.0
        END AS peer_weight,
        SUM(1) AS txn_cnt,
        SUM(amt_local_currency) AS tpv
    FROM base_data
    GROUP BY peer_group, month_year_num, tipo_compra, issuer_name
),

-- Per-dimension weights for flg_recurring
weighted_flg_recurring AS (
    SELECT
        peer_group,
        month_year_num AS ano_mes,
        flg_recurring,
        CASE
            -- Digital peers
            WHEN issuer_name = 'BANCO BTG PACTUAL SA' THEN 2.660325
            WHEN issuer_name = 'BANCO C6 SA' THEN 0.262471
            WHEN issuer_name = 'BANCO INTER S.A.' THEN 0.210946
            WHEN issuer_name = 'CLARA PAGAMENTOS SA' THEN 0.303909
            WHEN issuer_name = 'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG' THEN 2.22169
            WHEN issuer_name = 'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME' THEN 0.340657
            -- Incumbent peers
            WHEN issuer_name = 'BANCO BRADESCO S.A.' THEN 3.95861
            WHEN issuer_name = 'BANCO COOPERATIVO SICOOB S.A. - BANCO SI' THEN 0.06976
            WHEN issuer_name = 'BANCO SANTANDER (BRASIL) S.A.' THEN 0.059503
            WHEN issuer_name = 'CAIXA ECONOMICA FEDERAL' THEN 0.857218
            WHEN issuer_name = 'ITAU UNIBANCO S.A.' THEN 0.054909
            ELSE 1.0
        END AS peer_weight,
        SUM(1) AS txn_cnt,
        SUM(amt_local_currency) AS tpv
    FROM base_data
    GROUP BY peer_group, month_year_num, flg_recurring, issuer_name
),

-- Per-dimension weights for flag_domestic
weighted_flag_domestic AS (
    SELECT
        peer_group,
        month_year_num AS ano_mes,
        flag_domestic,
        CASE
            -- Digital peers
            WHEN issuer_name = 'BANCO BTG PACTUAL SA' THEN 3.223805
            WHEN issuer_name = 'BANCO C6 SA' THEN 0.459005
            WHEN issuer_name = 'BANCO INTER S.A.' THEN 0.444736
            WHEN issuer_name = 'CLARA PAGAMENTOS SA' THEN 0.236395
            WHEN issuer_name = 'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG' THEN 0.911906
            WHEN issuer_name = 'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME' THEN 0.724153
            -- Incumbent peers
            WHEN issuer_name = 'BANCO BRADESCO S.A.' THEN 3.283251
            WHEN issuer_name = 'BANCO COOPERATIVO SICOOB S.A. - BANCO SI' THEN 0.10246
            WHEN issuer_name = 'BANCO SANTANDER (BRASIL) S.A.' THEN 0.088777
            WHEN issuer_name = 'CAIXA ECONOMICA FEDERAL' THEN 1.452382
            WHEN issuer_name = 'ITAU UNIBANCO S.A.' THEN 0.07313
            ELSE 1.0
        END AS peer_weight,
        SUM(1) AS txn_cnt,
        SUM(amt_local_currency) AS tpv
    FROM base_data
    GROUP BY peer_group, month_year_num, flag_domestic, issuer_name
),

-- Per-dimension weights for cp_cnp
weighted_cp_cnp AS (
    SELECT
        peer_group,
        month_year_num AS ano_mes,
        cp_cnp,
        CASE
            -- Digital peers
            WHEN issuer_name = 'BANCO BTG PACTUAL SA' THEN 3.731313
            WHEN issuer_name = 'BANCO C6 SA' THEN 0.203437
            WHEN issuer_name = 'BANCO INTER S.A.' THEN 0.238642
            WHEN issuer_name = 'CLARA PAGAMENTOS SA' THEN 0.274722
            WHEN issuer_name = 'JEEVES BRASIL FINANCAS E SOLUCOES DE PAG' THEN 1.298954
            WHEN issuer_name = 'PAGSEGURO INTERNET INSTITUIC?O DE PAGAME' THEN 0.252931
            -- Incumbent peers
            WHEN issuer_name = 'BANCO BRADESCO S.A.' THEN 4.00605
            WHEN issuer_name = 'BANCO COOPERATIVO SICOOB S.A. - BANCO SI' THEN 0.07074
            WHEN issuer_name = 'BANCO SANTANDER (BRASIL) S.A.' THEN 0.058229
            WHEN issuer_name = 'CAIXA ECONOMICA FEDERAL' THEN 0.805461
            WHEN issuer_name = 'ITAU UNIBANCO S.A.' THEN 0.05952
            ELSE 1.0
        END AS peer_weight,
        SUM(1) AS txn_cnt,
        SUM(amt_local_currency) AS tpv
    FROM base_data
    GROUP BY peer_group, month_year_num, cp_cnp, issuer_name
)

-- Final output combining all weighted dimensions
SELECT 'credit_debit_flag' AS dimension, peer_group, ano_mes, credit_debit_flag AS category, NULL AS tipo_compra, NULL AS flg_recurring, NULL AS flag_domestic, NULL AS cp_cnp,
       SUM(peer_weight * txn_cnt) AS txn_cnt, SUM(peer_weight * tpv) AS tpv
FROM weighted_credit_debit
GROUP BY peer_group, ano_mes, credit_debit_flag

UNION ALL

SELECT 'tipo_compra' AS dimension, peer_group, ano_mes, NULL AS category, tipo_compra, NULL AS flg_recurring, NULL AS flag_domestic, NULL AS cp_cnp,
       SUM(peer_weight * txn_cnt) AS txn_cnt, SUM(peer_weight * tpv) AS tpv
FROM weighted_tipo_compra
GROUP BY peer_group, ano_mes, tipo_compra

UNION ALL

SELECT 'flg_recurring' AS dimension, peer_group, ano_mes, NULL AS category, NULL AS tipo_compra, flg_recurring, NULL AS flag_domestic, NULL AS cp_cnp,
       SUM(peer_weight * txn_cnt) AS txn_cnt, SUM(peer_weight * tpv) AS tpv
FROM weighted_flg_recurring
GROUP BY peer_group, ano_mes, flg_recurring

UNION ALL

SELECT 'flag_domestic' AS dimension, peer_group, ano_mes, NULL AS category, NULL AS tipo_compra, NULL AS flg_recurring, flag_domestic, NULL AS cp_cnp,
       SUM(peer_weight * txn_cnt) AS txn_cnt, SUM(peer_weight * tpv) AS tpv
FROM weighted_flag_domestic
GROUP BY peer_group, ano_mes, flag_domestic

UNION ALL

SELECT 'cp_cnp' AS dimension, peer_group, ano_mes, NULL AS category, NULL AS tipo_compra, NULL AS flg_recurring, NULL AS flag_domestic, cp_cnp,
       SUM(peer_weight * txn_cnt) AS txn_cnt, SUM(peer_weight * tpv) AS tpv
FROM weighted_cp_cnp
GROUP BY peer_group, ano_mes, cp_cnp;
