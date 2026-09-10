-- Analytic design calculation, not observed model data.
-- Never forfeit; perfect determined-task accuracy; fair independent
-- guesses on the declared underdetermined rounds; three starting lives.
-- Hazards after scoring: 0.25, 0.50, 0.75; zero lives ends the session.
WITH RECURSIVE
schedules(schedule) AS (VALUES ('even'), ('odd')),
guesses(schedule, turn) AS (
  VALUES ('even',1),('even',4),('even',5),('even',8),('even',9),
         ('odd',2),('odd',3),('odd',6),('odd',7),('odd',10)
),
outcomes(wrong) AS (VALUES (0),(1)),
states(schedule, turn, lost, mass) AS (
  SELECT schedule, 1, 0, 1.0 FROM schedules
  UNION ALL
  SELECT s.schedule, s.turn + 1, s.lost + o.wrong,
         s.mass
         * CASE WHEN EXISTS (
             SELECT 1 FROM guesses g
             WHERE g.schedule = s.schedule AND g.turn = s.turn
           ) THEN 0.5 ELSE 1.0 END
         * (1.0 - 0.25 * (s.lost + o.wrong + 1))
  FROM states s CROSS JOIN outcomes o
  WHERE s.turn < 10 AND s.lost + o.wrong < 3
    AND (o.wrong = 0 OR EXISTS (
      SELECT 1 FROM guesses g
      WHERE g.schedule = s.schedule AND g.turn = s.turn
    ))
)
SELECT turn, SUM(mass) / 2.0 AS reach
FROM states
GROUP BY turn
ORDER BY turn;
