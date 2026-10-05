;; Reads standard input once (up to 60000 bytes) and writes it to standard output.
(module
  (import "wasi_snapshot_preview1" "fd_read" (func $fd_read (param i32 i32 i32 i32) (result i32)))
  (import "wasi_snapshot_preview1" "fd_write" (func $fd_write (param i32 i32 i32 i32) (result i32)))
  (memory (export "memory") 1)
  (func (export "_start")
    ;; one iovec at 0: the buffer is at 64 and holds 60000 bytes; the count read lands at 16
    (i32.store (i32.const 0) (i32.const 64))
    (i32.store (i32.const 4) (i32.const 60000))
    (drop (call $fd_read (i32.const 0) (i32.const 0) (i32.const 1) (i32.const 16)))
    (i32.store (i32.const 4) (i32.load (i32.const 16)))
    (drop (call $fd_write (i32.const 1) (i32.const 0) (i32.const 1) (i32.const 20)))))
