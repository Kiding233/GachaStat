export const meta = {
  name: 'ascii-test',
  description: 'Test if ASCII-only workflows work',
  phases: [{ title: 'Test', detail: 'Simple test phase' }],
}

phase('Test')
log('ASCII workflow test - if you see this, ASCII workflows work.')
const result = await agent('Say hello in one word.', { label: 'test-agent', phase: 'Test' })
log('Agent said: ' + (result || 'null'))
