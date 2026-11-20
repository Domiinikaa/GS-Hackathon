// Sztuczne dane: 4 reguły z treści zadania ("Example rules, in plain words").
// TODO: gdy backend będzie gotowy, zamienić na fetch('/api/rules').
import { Rule } from './ruleTypes';

export const MOCK_RULES: Rule[] = [
  {
    id: 'settlements-prod',
    name: 'Settlement workflow failed in prod',
    team: 'Settlements',
    enabled: true,
    condition: {
      and: [
        { field: 'type', op: 'eq', value: 'WORKFLOW_FAILED' },
        { field: 'workflowName', op: 'eq', value: 'order-settlement' },
        { field: 'environment', op: 'eq', value: 'prod' },
      ],
    },
    channels: ['phone', 'sms', 'ui'],
    title: 'Workflow {{workflowName}} failed at step {{step}}',
    body: '{{error.message}}',
    severity: 'critical',
    color: 'red',
  },
  {
    id: 'pricing-warnings',
    name: 'Pricing engine warnings',
    team: 'Pricing',
    enabled: true,
    condition: {
      and: [
        { field: 'service', op: 'wildcard', value: 'pricing-engine-*' },
        { field: 'level', op: 'in', value: ['WARN', 'ERROR', 'FATAL'] },
      ],
    },
    channels: ['ui'],
    title: 'Pricing warnings for {{instrument}}',
    severity: 'warning',
    color: 'amber',
    group_by: 'instrument',
    group_window_s: 300,
  },
  {
    id: 'rates-big-rejections',
    name: 'Large rejected trades (rates desk)',
    team: 'Rates',
    enabled: true,
    condition: {
      and: [
        { field: 'meta.schema', op: 'wildcard', value: 'trade.rejected.*' },
        { field: 'payload.desk', op: 'eq', value: 'rates' },
        { field: 'payload.notional', op: 'gt', value: 10000000 },
      ],
    },
    channels: ['email', 'ui'],
    title: 'Rejected {{payload.currency}} {{payload.notional}} — {{payload.reason}}',
    severity: 'warning',
    color: 'amber',
  },
  {
    id: 'anna-payments-critical',
    name: 'Critical payments-api alerts',
    team: 'Anna (personal)',
    enabled: true,
    condition: {
      and: [
        { field: 'labels.service', op: 'eq', value: 'payments-api' },
        { field: 'labels.severity', op: 'eq', value: 'critical' },
      ],
    },
    // SMS tylko 8:00–20:00, poza tym email – to ustawimy w preferencjach kanałów (zadanie 4)
    channels: ['sms'],
    title: '{{alertname}} on {{labels.service}}',
    body: '{{annotations.summary}}',
    severity: 'critical',
    color: 'red',
  },
];
