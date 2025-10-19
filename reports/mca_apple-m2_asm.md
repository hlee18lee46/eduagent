## llvm-mca report (apple-m2)

```text
warning: found a return instruction in the input assembly sequence.
note: program counter updates are ignored.
Iterations:        100
Instructions:      200
Total Cycles:      103
Total uOps:        200

Dispatch Width:    6
uOps Per Cycle:    1.94
IPC:               1.94
Block RThroughput: 1.0


Instruction Info:
[1]: #uOps
[2]: Latency
[3]: RThroughput
[4]: MayLoad
[5]: MayStore
[6]: HasSideEffects (U)

[1]    [2]    [3]    [4]    [5]    [6]    Instructions:
 1      2     1.00                        add	x0, x1, x2
 1      0     1.00                  U     ret


Resources:
[0.0] - CyUnitB
[0.1] - CyUnitB
[1]   - CyUnitBR
[2.0] - CyUnitFloatDiv
[2.1] - CyUnitFloatDiv
[3.0] - CyUnitI
[3.1] - CyUnitI
[3.2] - CyUnitI
[3.3] - CyUnitI
[4]   - CyUnitID
[5]   - CyUnitIM
[6.0] - CyUnitIS
[6.1] - CyUnitIS
[7]   - CyUnitIntDiv
[8.0] - CyUnitLS
[8.1] - CyUnitLS
[9.0] - CyUnitV
[9.1] - CyUnitV
[9.2] - CyUnitV
[10]  - CyUnitVC
[11]  - CyUnitVD
[12.0] - CyUnitVM
[12.1] - CyUnitVM


Resource pressure per iteration:
[0.0]  [0.1]  [1]    [2.0]  [2.1]  [3.0]  [3.1]  [3.2]  [3.3]  [4]    [5]    [6.0]  [6.1]  [7]    [8.0]  [8.1]  [9.0]  [9.1]  [9.2]  [10]   [11]   [12.0] [12.1] 
0.50   0.50   1.00    -      -     0.50   1.00   0.50   1.00    -      -     1.00   1.00    -      -      -      -      -      -      -      -      -      -     

Resource pressure by instruction:
[0.0]  [0.1]  [1]    [2.0]  [2.1]  [3.0]  [3.1]  [3.2]  [3.3]  [4]    [5]    [6.0]  [6.1]  [7]    [8.0]  [8.1]  [9.0]  [9.1]  [9.2]  [10]   [11]   [12.0] [12.1] Instructions:
 -      -      -      -      -      -     1.00    -     1.00    -      -     1.00   1.00    -      -      -      -      -      -      -      -      -      -     add	x0, x1, x2
0.50   0.50   1.00    -      -     0.50    -     0.50    -      -      -      -      -      -      -      -      -      -      -      -      -      -      -     ret

```

### Timeline (apple-m2)

```text
warning: found a return instruction in the input assembly sequence.
note: program counter updates are ignored.
Iterations:        100
Instructions:      200
Total Cycles:      103
Total uOps:        200

Dispatch Width:    6
uOps Per Cycle:    1.94
IPC:               1.94
Block RThroughput: 1.0


Instruction Info:
[1]: #uOps
[2]: Latency
[3]: RThroughput
[4]: MayLoad
[5]: MayStore
[6]: HasSideEffects (U)

[1]    [2]    [3]    [4]    [5]    [6]    Instructions:
 1      2     1.00                        add	x0, x1, x2
 1      0     1.00                  U     ret


Resources:
[0.0] - CyUnitB
[0.1] - CyUnitB
[1]   - CyUnitBR
[2.0] - CyUnitFloatDiv
[2.1] - CyUnitFloatDiv
[3.0] - CyUnitI
[3.1] - CyUnitI
[3.2] - CyUnitI
[3.3] - CyUnitI
[4]   - CyUnitID
[5]   - CyUnitIM
[6.0] - CyUnitIS
[6.1] - CyUnitIS
[7]   - CyUnitIntDiv
[8.0] - CyUnitLS
[8.1] - CyUnitLS
[9.0] - CyUnitV
[9.1] - CyUnitV
[9.2] - CyUnitV
[10]  - CyUnitVC
[11]  - CyUnitVD
[12.0] - CyUnitVM
[12.1] - CyUnitVM


Resource pressure per iteration:
[0.0]  [0.1]  [1]    [2.0]  [2.1]  [3.0]  [3.1]  [3.2]  [3.3]  [4]    [5]    [6.0]  [6.1]  [7]    [8.0]  [8.1]  [9.0]  [9.1]  [9.2]  [10]   [11]   [12.0] [12.1] 
0.50   0.50   1.00    -      -     0.50   1.00   0.50   1.00    -      -     1.00   1.00    -      -      -      -      -      -      -      -      -      -     

Resource pressure by instruction:
[0.0]  [0.1]  [1]    [2.0]  [2.1]  [3.0]  [3.1]  [3.2]  [3.3]  [4]    [5]    [6.0]  [6.1]  [7]    [8.0]  [8.1]  [9.0]  [9.1]  [9.2]  [10]   [11]   [12.0] [12.1] Instructions:
 -      -      -      -      -      -     1.00    -     1.00    -      -     1.00   1.00    -      -      -      -      -      -      -      -      -      -     add	x0, x1, x2
0.50   0.50   1.00    -      -     0.50    -     0.50    -      -      -      -      -      -      -      -      -      -      -      -      -      -      -     ret


Timeline view:
                    012
Index     0123456789   

[0,0]     DeeER.    . .   add	x0, x1, x2
[0,1]     DE--R.    . .   ret
[1,0]     DeeER.    . .   add	x0, x1, x2
[1,1]     D=E-R.    . .   ret
[2,0]     D==eeER   . .   add	x0, x1, x2
[2,1]     D==E--R   . .   ret
[3,0]     .D=eeER   . .   add	x0, x1, x2
[3,1]     .D==E-R   . .   ret
[4,0]     .D===eeER . .   add	x0, x1, x2
[4,1]     .D===E--R . .   ret
[5,0]     .D===eeER . .   add	x0, x1, x2
[5,1]     .D====E-R . .   ret
[6,0]     . D====eeER .   add	x0, x1, x2
[6,1]     . D====E--R .   ret
[7,0]     . D====eeER .   add	x0, x1, x2
[7,1]     . D=====E-R .   ret
[8,0]     . D======eeER   add	x0, x1, x2
[8,1]     . D======E--R   ret
[9,0]     .  D=====eeER   add	x0, x1, x2
[9,1]     .  D======E-R   ret


Average Wait times (based on the timeline view):
[0]: Executions
[1]: Average time spent waiting in a scheduler's queue
[2]: Average time spent waiting in a scheduler's queue while ready
[3]: Average time elapsed from WB until retire stage

      [0]    [1]    [2]    [3]
0.     10    3.8    3.8    0.0       add	x0, x1, x2
1.     10    4.3    4.3    1.5       ret
       10    4.1    4.1    0.8       <total>

```
