/** One ordered stream shared by typed and spoken commands. Stop cancels pending
 * work, never pretends to undo a mutation already accepted by the server. */
export class VoiceCommandQueue {
  private tail: Promise<void> = Promise.resolve();
  private generation = 0;
  private accountingEpoch = 0;
  pending = 0;
  constructor(private changed: (pending: number) => void = () => {},
    private limits: {maxPending?:number;maxAgeMs?:number;now?:()=>number} = {}) {}
  clear() { this.generation++; }
  /** Detach an unresponsive task. Callers must invalidate its eventual results. */
  reset() { this.generation++; this.accountingEpoch++; this.tail=Promise.resolve(); this.pending=0; this.changed(0); }
  enqueue(run: () => Promise<void>) {
    if(this.pending >= (this.limits.maxPending ?? Infinity))return Promise.reject(Error('Очередь заполнена. Дождитесь выполнения или остановите команды.'));
    const now=this.limits.now??(()=>performance.now()),created=now();
    const generation = this.generation;
    const accountingEpoch = this.accountingEpoch;
    this.changed(++this.pending);
    const task = this.tail.then(async () => {
      if (generation !== this.generation) return;
      if(now()-created > (this.limits.maxAgeMs??Infinity)){
        this.clear();
        throw Error('Команда устарела. Следующие команды очереди отменены; повторите выбор объекта.');
      }
      await run();
    });
    this.tail = task.catch(() => {}).finally(() => { if(accountingEpoch===this.accountingEpoch) this.changed(--this.pending); });
    return task;
  }
}
