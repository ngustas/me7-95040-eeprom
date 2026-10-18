//@category ME7
// For each CALLS to a target, walk back over the basic block collecting the last
// immediate loaded into each of R12..R15, so we can read off (len, eeAddr, ptr).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.lang.Register;
import ghidra.program.model.symbol.*;
import java.util.*;

public class CallArgs extends GhidraScript {

    static final int BACK = 40;   // instructions to walk back

    @Override public void run() throws Exception {
        for (String a : getScriptArgs()) {
            long v = Long.decode(a);
            Address t = addr(v);
            Function tf = getFunctionContaining(t);
            println("\n======== callers of " + a + " (" + (tf==null?"?":tf.getName()) + ") ========");

            List<Address> sites = new ArrayList<>();
            for (Reference r : getReferencesTo(t))
                if (r.getReferenceType().isCall()) sites.add(r.getFromAddress());
            Collections.sort(sites);
            println("call sites: " + sites.size());

            for (Address cs : sites) {
                Function cf = getFunctionContaining(cs);
                Map<String,String> regs = backtrack(cs);
                StringBuilder sb = new StringBuilder();
                for (String rn : new String[]{"r12","r13","r14","r15"}) {
                    String val = regs.get(rn);
                    sb.append(String.format("%s=%-12s", rn, val==null?"?":val));
                }
                String ee = regs.get("r13");
                String pg = "";
                if (ee != null && ee.startsWith("#")) {
                    try {
                        long x = Long.decode(ee.substring(1));
                        if (x % 16 == 0 && x < 0x200) pg = String.format("  >>> PAGE %d (0x%03X)", x/16, x);
                        else pg = String.format("  >>> addr 0x%03X (page %d + %d)", x, x/16, x%16);
                    } catch (Exception e) {}
                }
                println(String.format(" %s  [%s]  %s%s", cs,
                        cf==null?"-":cf.getName(), sb.toString(), pg));
            }
        }
    }

    /** last immediate / simple source assigned to r12..r15 before the call */
    private Map<String,String> backtrack(Address call) {
        Map<String,String> out = new HashMap<>();
        Set<String> want = new HashSet<>(Arrays.asList("r12","r13","r14","r15"));
        Instruction ins = getInstructionBefore(call);
        int n = 0;
        while (ins != null && n < BACK && !want.isEmpty()) {
            n++;
            String m = ins.getMnemonicString().toLowerCase();
            // stop at control flow joins / calls that clobber
            if (m.startsWith("calls") || m.startsWith("call")) break;
            if (ins.getNumOperands() >= 2) {
                Object[] d = ins.getOpObjects(0);
                if (d.length == 1 && d[0] instanceof Register) {
                    String rn = ((Register)d[0]).getName().toLowerCase();
                    if (want.contains(rn)) {
                        Object[] s = ins.getOpObjects(1);
                        String val;
                        if (m.equals("mov") || m.equals("movb") || m.equals("movbz") || m.equals("movbs")) {
                            if (s.length == 1 && s[0] instanceof Scalar)
                                val = "#0x" + Long.toHexString(((Scalar)s[0]).getUnsignedValue());
                            else val = ins.getDefaultOperandRepresentation(1);
                        } else {
                            val = "<" + m + " " + ins.getDefaultOperandRepresentation(1) + ">";
                        }
                        out.put(rn, val);
                        want.remove(rn);
                    }
                }
            }
            ins = getInstructionBefore(ins.getAddress());
        }
        return out;
    }

    private Address addr(long v){ return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v); }
}
