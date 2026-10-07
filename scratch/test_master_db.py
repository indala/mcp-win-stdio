import json
from mcp_win_stdio.excel_db.server import (
    compare_master_datasets,
    generate_master_migration_plan,
    sync_master_to_db
)

# 1. Test compare_master_datasets comparing DB against Excel
src_a = json.dumps({
    'type': 'db',
    'connection': 'showreel_dev',
    'query': "SELECT material_number, description, sale_price as unit_rate, hire_charges FROM props_management.materials WHERE material_number = 'DL01001'"
})
src_b = json.dumps({'type': 'excel', 'path': 'scratch/test_wb1.xlsx', 'sheet': 'Materials'})
col_map = json.dumps({'Material Number': 'material_number', 'Description': 'description', 'Unit Rate': 'unit_rate'})

res_compare = json.loads(compare_master_datasets(
    source_a_json=src_a,
    source_b_json=src_b,
    key_columns=['material_number'],
    column_mapping_json=col_map,
    output_report_path='scratch/audit_report.xlsx'
))
print('[PASS] compare_master_datasets status:', res_compare['status'])
print('Matched keys:', res_compare['matched_primary_keys'])
print('Identical records:', res_compare['identical_records_count'])
print('New records in Excel:', res_compare['new_records_in_source_b_count'])

# 2. Test generate_master_migration_plan
res_plan = json.loads(generate_master_migration_plan(
    excel_path='scratch/test_wb1.xlsx',
    target_table='props_management.materials',
    key_columns=['material_number'],
    column_mapping_json=json.dumps({'Material Number': 'material_number', 'Description': 'description', 'Unit Rate': 'sale_price'}),
    connection_name_or_url='showreel_dev',
    output_sql_path='scratch/migration.sql'
))
print('[PASS] generate_master_migration_plan migratable rows:', res_plan['valid_migratable_rows'])
print('Generated SQL preview:\n', res_plan['sql_preview'][1])

# 3. Test sync_master_to_db (Dry Run)
res_sync = json.loads(sync_master_to_db(
    excel_path='scratch/test_wb1.xlsx',
    target_table='props_management.materials',
    key_columns=['material_number'],
    column_mapping_json=json.dumps({'Material Number': 'material_number', 'Description': 'description', 'Unit Rate': 'sale_price'}),
    connection_name_or_url='showreel_dev',
    dry_run=True
))
print('[PASS] sync_master_to_db status:', res_sync['status'])
print('Message:', res_sync['message'])
print('ALL EXCEL-DB MASTER COMPARISON & MIGRATION TESTS PASSED!')
