//@category ME7
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;

public class Lst extends GhidraScript {
    @Override public void run() throws Exception {
        String[] a = getScriptArgs();
        for (int i=0;i+1<a.length;i+=2) {
            long s = Long.decode(a[i]), e = Long.decode(a[i+1]);
            println(String.format("\n==== listing 0x%06X - 0x%06X ====", s, e));
            Address ad = addr(s);
            while (ad != null && ad.getOffset() <= e) {
                Instruction ins = getInstructionAt(ad);
                if (ins == null) { ad = ad.add(1); continue; }
                StringBuilder b = new StringBuilder();
                for (byte x : ins.getBytes()) b.append(String.format("%02x ", x));
                println(String.format("  %s  %-38s %s", ad, ins.toString(), b.toString()));
                ad = ins.getMaxAddress().add(1);
            }
        }
    }
    private Address addr(long v){ return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v); }
}
