-- Fake v2 data (no real farm). Passwords: "motdepasse-test" (bcrypt, cost 4).
INSERT INTO fermes (name, userpass, farmname, adress, integration_year, last_login_date) VALUES
    ('a',          '$2b$04$iuPH3PbQRT7BYqThzyfY2efK7Z8qvC5RaQ3FANqxYaqE3P6TIODRm', 'Ferme des Essais', 'Montrottier', '2022', '2026-03-14 23:26'),
    ('lucie',      '$2b$04$iuPH3PbQRT7BYqThzyfY2efK7Z8qvC5RaQ3FANqxYaqE3P6TIODRm', 'GAEC du Coteau',   'Aveize',      '2020', NULL),
    ('marc.terre', '$2b$04$iuPH3PbQRT7BYqThzyfY2efK7Z8qvC5RaQ3FANqxYaqE3P6TIODRm', 'Les Jardins Haut', 'Larajasse',   '2023', NULL);

INSERT INTO surface (linked_id, year, surftot, surffr, surfgf, surfleg, prairie, culture, surfautre) VALUES
    (1, 2024, 18, 0.2, 0, 0, 11, 4.8, 2),
    (1, 2025, 18, 0.3, 0, 0.01, 11, 4.69, 2),
    (2, 2025, 9.5, 1.2, 0.8, 0.5, 5, 1, 1);

INSERT INTO coefbiodiv (year, coefhaie, coefarbrealign, coefarbreseul, coefbosquet, coefmare, coeffosse,
                        coefbordure, coefjachere, coefjacheremel, coefmuret, coefprairie, description) VALUES
    (2025, 0.01, 0.01, 0.1, 0.001, 0.01, 0.01, 0.005, 0.001, 0.005, 0.005, 0.001, 'coefficients de test');

INSERT INTO biodiv (linked_id, year, haie, arbrealign, arbreseul, bosquet, mare, fosse, bordure, jachere,
                    jacheremel, muret, description, biodivscore) VALUES
    (1, 2025, 1200, 300, 14, 2500, 1, 0, 800, 0, 0, 40, 'haies replantées', 22.4);
