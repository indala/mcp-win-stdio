-- Migration Script for props_management.materials
-- Generated from test_wb1.xlsx at 2026-10-07T15:55:01.522982
BEGIN;

INSERT INTO props_management.materials (material_number, description, sale_price)
VALUES ('DL01001', 'LED-DURA LIGHT', 129.98)
ON CONFLICT (material_number) DO UPDATE SET
    description = EXCLUDED.description,
    sale_price = EXCLUDED.sale_price;
INSERT INTO props_management.materials (material_number, description, sale_price)
VALUES ('DL01002', 'POWER SUPPLY', 450.0)
ON CONFLICT (material_number) DO UPDATE SET
    description = EXCLUDED.description,
    sale_price = EXCLUDED.sale_price;

COMMIT;
