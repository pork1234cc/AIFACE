import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compactConfig, materialSlots, nextMaterialSlot } from '../src/lib/creation-config.ts';
import type { OrderDetail } from '../src/types/orders.ts';

test('继续修改不得把结果滚回左侧', () => {
  const page = readFileSync(new URL('../src/app/orders/[id]/page.tsx', import.meta.url), 'utf8');
  assert.doesNotMatch(page, /scrollIntoView/);
});

test('素材空位不改变编号，旧修改要求完整转为文字', () => {
  const order = { params: { schema_version: 2, base_asset_id: 'generated', style_id: null,
    material_slots: [null, 'hair', 'coat'], aspect_ratio: '1:1', extra_requirement: '保持背景',
    changes: [{ target_description: '左侧人物', change_type: '发型', source_asset_ids: ['hair'], instruction: '替换发型', preserve_instruction: '保留脸部' }] }, assets: [] } as unknown as OrderDetail;
  assert.deepEqual(materialSlots(order), [null, 'hair', 'coat']);
  const config = compactConfig(order);
  assert.match(config.extra_requirement, /使用素材2/);
  assert.match(config.extra_requirement, /保留脸部/);
  assert.match(config.extra_requirement, /保持背景/);
  assert.deepEqual(config.changes, []);
  assert.equal(config.base_asset_id, 'generated');
  assert.equal(config.output_format, 'png');
});

test('素材位置超过三张时保留顺序与格式', () => {
  const order = { params: { schema_version: 2, base_asset_id: 'main', style_id: null,
    material_slots: ['a', null, 'c', 'd', 'e'], aspect_ratio: '1:1', output_format: 'jpeg',
    extra_requirement: '', changes: [] }, assets: [] } as unknown as OrderDetail;
  assert.deepEqual(materialSlots(order), ['a', null, 'c', 'd', 'e']);
  assert.equal(compactConfig(order).output_format, 'jpeg');
});

test('上传入口优先补空号，已有素材编号不改变', () => {
  const order = { params: { material_slots: ['a', null, 'c', 'd'] }, assets: [
    { id: 'a', kind: 'input', input_role: 'material', is_active_input: true },
    { id: 'c', kind: 'input', input_role: 'material', is_active_input: true },
    { id: 'd', kind: 'input', input_role: 'material', is_active_input: true },
  ] } as unknown as OrderDetail;
  assert.equal(nextMaterialSlot(order), '2');
  assert.deepEqual(materialSlots(order), ['a', null, 'c', 'd']);
  order.params.material_slots = ['a', 'b', 'c', 'd'];
  order.assets.push({ id: 'b', kind: 'input', input_role: 'material', is_active_input: true } as OrderDetail['assets'][number]);
  assert.equal(nextMaterialSlot(order), '5');
});

test('主图片上传区仅取活动原始输入，不展示生成图', () => {
  const code = readFileSync(new URL('../src/components/orders/asset-panel.tsx', import.meta.url), 'utf8');
  assert.match(code, /asset.kind === "input" && asset.is_active_input/);
  assert.match(code, /asset.input_role === "main"/);
  assert.doesNotMatch(code, /base_asset_id/);
});
