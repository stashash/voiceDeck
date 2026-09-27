/** One ordered stream shared by typed and spoken commands. Stop cancels pending
 * work, never pretends to undo a mutation already accepted by the server. */
export class VoiceCommandQueue {
  private tail: Promise<void> = Promise.resolve();
  private generation = 0;
  private accountingEpoch = 0;
  pending = 0;
  constructor(private changed: (pending: number) => void = () => {}) {}
  clear() { this.generation++; }
  /** Detach an unresponsive task. Callers must invalidate its eventual results. */
  reset() { this.generation++; this.accountingEpoch++; this.tail=Promise.resolve(); this.pending=0; this.changed(0); }
  enqueue(run: () => Promise<void>) {
    const generation = this.generation;
    const accountingEpoch = this.accountingEpoch;
    this.changed(++this.pending);
    const task = this.tail.then(async () => {
      if (generation === this.generation) await run();
    });
    this.tail = task.catch(() => {}).finally(() => { if(accountingEpoch===this.accountingEpoch) this.changed(--this.pending); });
    return task;
  }
}
