//@category ME7
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.util.*;

public class ShadowRefs extends GhidraScript {

    static final int  BASE16 = 0xBDA8;          // 16-bit DPP2 address
    static final long PHYS   = 0x383DA8L;       // resolved
    static final int  NSLOT  = 0x15;

    // page attribute table -> id per page
    static final long ATTR = 0x816E00L;

    @Override public void run() throws Exception {
        // map record id -> pages
        Map<Integer,List<Integer>> idPages = new TreeMap<>();
        for (int p=0;p<32;p++) {
            int w = getShort(addr(ATTR + p*2)) & 0xFFFF;
            idPages.computeIfAbsent(w>>8, k->new ArrayList<Integer>()).add(p);
        }

        // collect hits: offset-in-shadow -> list of "addr func instr"
        Map<Integer,List<String>> hits = new TreeMap<>();

        // (a) references to the physical range
        ReferenceManager rm = currentProgram.getReferenceManager();
        for (int off=0; off<NSLOT*16; off++) {
            Address a = addr(PHYS + off);
            ReferenceIterator ri = rm.getReferencesTo(a);
            while (ri.hasNext()) {
                Reference r = ri.next();
                Instruction ins = getInstructionAt(r.getFromAddress());
                if (ins == null) continue;
                Function f = getFunctionContaining(r.getFromAddress());
                hits.computeIfAbsent(off,k->new ArrayList<String>())
                    .add(String.format("%s %-34s [%s] (ref)", r.getFromAddress(), ins.toString(),
                         f==null?"-":f.getName()));
            }
        }

        // (b) raw 16-bit operand scalars in range (catches un-DPP'd accesses)
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next();
            for (int op=0; op<ins.getNumOperands(); op++) {
                for (Object o : ins.getOpObjects(op)) {
                    long v = -1;
                    if (o instanceof Scalar) v = ((Scalar)o).getUnsignedValue();
                    else if (o instanceof Address) {
                        long ao = ((Address)o).getOffset();
                        v = (ao >= PHYS && ao < PHYS+NSLOT*16) ? (ao - PHYS + BASE16) : -1;
                    }
                    if (v >= BASE16 && v < BASE16 + NSLOT*16) {
                        int off = (int)(v - BASE16);
                        Function f = getFunctionContaining(ins.getAddress());
                        String line = String.format("%s %-34s [%s] (imm)", ins.getAddress(), ins.toString(),
                             f==null?"-":f.getName());
                        List<String> l = hits.computeIfAbsent(off,k->new ArrayList<String>());
                        boolean dup=false;
                        for (String s : l) if (s.startsWith(ins.getAddress().toString())) dup=true;
                        if (!dup) l.add(line);
                    }
                }
            }
        }

        for (Map.Entry<Integer,List<Integer>> e : idPages.entrySet()) {
            int id = e.getKey();
            if (id == 0xFF) continue;
            println(String.format("\n=========== record 0x%02X  pages %s   shadow 0x%04X-0x%04X ===========",
                id, e.getValue(), BASE16+id*16, BASE16+id*16+15));
            boolean any=false;
            for (int b=0;b<16;b++) {
                int off = id*16 + b;
                List<String> l = hits.get(off);
                if (l == null) continue;
                any=true;
                println(String.format("  byte %2d (0x%04X):", b, BASE16+off));
                for (String s : l) println("      " + s);
            }
            if (!any) println("  (no direct references found)");
        }
    }
    private Address addr(long v){ return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v); }
}
