//@category ME7
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.util.*;

public class Xref16 extends GhidraScript {
    @Override public void run() throws Exception {
        Set<Long> want = new LinkedHashSet<>();
        Map<Long,Long> phys = new LinkedHashMap<>();
        for (String a : getScriptArgs()) {
            long v = Long.decode(a);
            want.add(v);
            // DPP2 = 0x00E0 covers 16-bit 0x8000-0xBFFF -> 0x380000 | (v & 0x3FFF)
            phys.put(v, 0x380000L | (v & 0x3FFF));
        }
        Map<Long,List<String>> out = new LinkedHashMap<>();
        for (long v : want) out.put(v, new ArrayList<String>());

        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            Set<Long> hit = new LinkedHashSet<>();
            for (int op=0; op<ins.getNumOperands(); op++)
                for (Object o : ins.getOpObjects(op)) {
                    if (o instanceof Scalar) { long x=((Scalar)o).getUnsignedValue(); if (want.contains(x)) hit.add(x); }
                    else if (o instanceof Address) {
                        long ao=((Address)o).getOffset();
                        for (Map.Entry<Long,Long> e : phys.entrySet()) if (e.getValue()==ao) hit.add(e.getKey());
                    }
                }
            for (Reference r : ins.getReferencesFrom()) {
                long ao = r.getToAddress().getOffset();
                for (Map.Entry<Long,Long> e : phys.entrySet()) if (e.getValue()==ao) hit.add(e.getKey());
            }
            for (long h : hit) {
                Function f = getFunctionContaining(ins.getAddress());
                out.get(h).add(String.format("%s %-36s [%s]", ins.getAddress(), ins.toString(),
                    f==null?"-":f.getName()));
            }
        }
        for (long v : want) {
            println(String.format("\n===== 0x%04X (phys 0x%06X) : %d hits =====", v, phys.get(v), out.get(v).size()));
            for (String s : out.get(v)) println("   " + s);
        }
    }
}
