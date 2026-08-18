-- Benchmarks SQL de ExpenseAI à exécuter avec psql après les deux imports.
-- Les temps doivent provenir de PostgreSQL réel : aucun résultat n'est inventé.

-- Les statistiques aident le planificateur à choisir un plan réaliste.
ANALYZE staging_expenses_raw;
ANALYZE expenses;

-- Choisir un groupe présent dans les deux structures. Les groupes techniques
-- créés par le preprocessing sont exclus car ils n'existent pas dans le brut.
SELECT e.expense_group, COUNT(*) AS normalized_line_count
FROM expenses AS e
WHERE EXISTS (
    SELECT 1
    FROM staging_expenses_raw AS s
    WHERE s.expense_number = e.expense_group
)
GROUP BY e.expense_group
ORDER BY normalized_line_count DESC, e.expense_group
LIMIT 10;

\set expense_group_value 'NSAS250800083'

-- ============================================================================
-- 1. BASELINE CONTRÔLÉE PUIS PLAN NORMAL SUR expenses
-- ============================================================================

-- Les parcours par index sont temporairement désactivés dans cette transaction.
-- Le plan devrait généralement contenir "Seq Scan". Observer les lignes filtrées,
-- Planning Time, Execution Time et BUFFERS.
BEGIN;
SET LOCAL enable_indexscan = off;
SET LOCAL enable_indexonlyscan = off;
SET LOCAL enable_bitmapscan = off;

EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM expenses
WHERE expense_group = :'expense_group_value';

ROLLBACK;

-- Fonctionnement normal : l'index ix_expenses_expense_group est disponible.
-- PostgreSQL reste libre de choisir un Seq Scan si la table est petite ou si le
-- filtre n'est pas assez sélectif.
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM expenses
WHERE expense_group = :'expense_group_value';

-- ============================================================================
-- 2. COMPARAISON FONCTIONNELLE : STRUCTURE BRUTE ET STRUCTURE NORMALISÉE
-- ============================================================================

-- staging_expenses_raw représente l'export brut : les valeurs métier sont en
-- TEXT, répétées ligne par ligne, et expense_number n'est volontairement pas
-- indexé. Une recherche sélective conduit généralement à analyser la table brute.
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM staging_expenses_raw
WHERE expense_number = :'expense_group_value';

-- expenses représente la structure optimisée : types PostgreSQL adaptés, clés
-- étrangères vers les référentiels et index sur expense_group.
EXPLAIN (ANALYZE, BUFFERS)
SELECT *
FROM expenses
WHERE expense_group = :'expense_group_value';

-- Les deux recherches répondent au même besoin fonctionnel (retrouver les lignes
-- d'une note), mais elles ne sont pas strictement identiques techniquement : les
-- tables n'ont ni les mêmes colonnes, ni les mêmes types, ni exactement le même
-- nombre de lignes après suppression du doublon complet.

-- Comparaison temporelle. La staging doit convertir son texte à l'exécution,
-- tandis que expenses possède une vraie colonne DATE indexée.
EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM staging_expenses_raw
WHERE expense_date::TIMESTAMP::DATE >= DATE '2026-01-01'
  AND expense_date::TIMESTAMP::DATE < DATE '2026-02-01';

EXPLAIN (ANALYZE, BUFFERS)
SELECT COUNT(*)
FROM expenses
WHERE expense_date >= DATE '2026-01-01'
  AND expense_date < DATE '2026-02-01';

-- Comparaison d'un calcul numérique. La structure brute convertit TEXT en
-- NUMERIC à chaque exécution ; la structure normalisée stocke déjà NUMERIC(14,2).
EXPLAIN (ANALYZE, BUFFERS)
SELECT AVG(amount_ttc_system_currency::NUMERIC(14, 2))
FROM staging_expenses_raw;

EXPLAIN (ANALYZE, BUFFERS)
SELECT AVG(amount_ttc)
FROM expenses;

-- Comparaison d'une agrégation par type. La staging répète le libellé complet sur
-- chaque ligne ; la structure normalisée le stocke une fois dans expense_types.
-- La normalisation réduit la redondance, sans garantir que toute jointure sera
-- systématiquement plus rapide sur un petit volume.
EXPLAIN (ANALYZE, BUFFERS)
SELECT expense_type, COUNT(*) AS expense_count
FROM staging_expenses_raw
GROUP BY expense_type
ORDER BY expense_count DESC;

EXPLAIN (ANALYZE, BUFFERS)
SELECT et.name, COUNT(*) AS expense_count
FROM expenses AS e
JOIN expense_types AS et ON et.id = e.expense_type_id
GROUP BY et.name
ORDER BY expense_count DESC;

-- ============================================================================
-- 3. GRILLE DE LECTURE POUR LE MÉMOIRE
-- ============================================================================

-- Pour chaque plan, relever sans les inventer :
--   * Seq Scan : lecture séquentielle de la table ;
--   * Index Scan / Bitmap Index Scan : accès guidé par un index ;
--   * Planning Time : temps nécessaire pour choisir le plan ;
--   * Execution Time : temps réellement consacré à l'exécution ;
--   * actual rows et Rows Removed by Filter : lignes trouvées ou filtrées ;
--   * BUFFERS : blocs trouvés en cache ou lus depuis le stockage.
--
-- Répéter les mesures plusieurs fois et signaler l'effet du cache. Les résultats
-- dépendent du serveur, des statistiques, de la taille des tables et de la
-- sélectivité. Une structure normalisée améliore la cohérence et réduit la
-- redondance ; un index améliore surtout les recherches suffisamment sélectives.
