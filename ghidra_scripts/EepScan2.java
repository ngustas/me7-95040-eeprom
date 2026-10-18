//@category ME7
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.*;
import java.util.*;

public class EepScan2 extends GhidraScript {

    static final long[] TARGETS = {
        0xFFCCL, 0xFFCEL,            // P6, DP6
        0xFFB2L,                     // SSCCON
        0xF0B0L, 0xF0B2L, 0xF0B4L,   // SSCTB, SSCRB, SSCBR  (ESFR)
        0xFF72L, 0xFF74L, 0xFF76L    // SSCTIC/RIC/EIC
    };
    static final String[] NAMES = {
        "P6","DP6","SSCCON","SSCTB","SSCRB","SSCBR","SSCTIC","SSCRIC","SSCEIC"
    };

    @Override
    public void run() throws Exception {
        println("=== symbols at target addresses ===");
        for (long t : TARGETS) {
            Address a = addr(t);
            Symbol[] ss = currentProgram.getSymbolTable().getSymbols(a);
            StringBuilder sb = new StringBuilder(String.format("  0x%04X -> ", t));
            if (ss.length==0) sb.append("(none)");
            for (Symbol s : ss) sb.append(s.getName()).append(" ");
            println(sb.toString());
        }

        println("\n=== references TO target addresses ===");
        ReferenceManager rm = currentProgram.getReferenceManager();
        for (int i=0;i<TARGETS.length;i++) {
            Address a = addr(TARGETS[i]);
            ReferenceIterator ri = rm.getReferencesTo(a);
            List<Reference> l = new ArrayList<>();
            while (ri.hasNext()) l.add(ri.next());
            println(String.format("--- 0x%04X (%s): %d refs ---", TARGETS[i],
                i<NAMES.length?NAMES[i]:"?", l.size()));
            for (Reference r : l) {
                Address fa = r.getFromAddress();
                Instruction ins = getInstructionAt(fa);
                Function f = getFunctionContaining(fa);
                println(String.format("   %s  %-36s %-10s [%s]", fa,
                    ins==null?"(data)":ins.toString(), r.getReferenceType(),
                    f==null?"-":f.getName()));
            }
        }

        println("\n=== operand-object scan (scalars / addresses matching targets) ===");
        Set<Long> want = new HashSet<>();
        for (long t: TARGETS) want.add(t);
        InstructionIterator it = currentProgram.getListing().getInstructions(true);
        int n=0, shown=0;
        while (it.hasNext() && !monitor.isCancelled()) {
            Instruction ins = it.next(); n++;
            boolean hit=false;
            for (int op=0; op<ins.getNumOperands() && !hit; op++) {
                for (Object o : ins.getOpObjects(op)) {
                    if (o instanceof Scalar && want.contains(((Scalar)o).getUnsignedValue())) { hit=true; break; }
                    if (o instanceof Address && want.contains(((Address)o).getOffset())) { hit=true; break; }
                }
            }
            if (hit) {
                shown++;
                if (shown<=400) {
                    Function f = getFunctionContaining(ins.getAddress());
                    println(String.format("   %s  %-36s [%s]", ins.getAddress(), ins.toString(),
                        f==null?"-":f.getName()));
                }
            }
        }
        println("scanned "+n+" instructions, operand hits: "+shown);

        println("\n=== rendering sample: first 40 instructions that reference ANY addr in 0xFE00-0xFFFF ===");
        it = currentProgram.getListing().getInstructions(true);
        int k=0;
        while (it.hasNext() && k<40 && !monitor.isCancelled()) {
            Instruction ins = it.next();
            for (Reference r : ins.getReferencesFrom()) {
                long off = r.getToAddress().getOffset();
                if (off>=0xFE00 && off<=0xFFFF) {
                    println(String.format("   %s  %-40s -> %s", ins.getAddress(), ins.toString(), r.getToAddress()));
                    k++; break;
                }
            }
        }
    }

    private Address addr(long v) {
        return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v);
    }
}
