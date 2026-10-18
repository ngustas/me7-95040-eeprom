//@category ME7
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.address.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;

public class Dec2 extends GhidraScript {
    @Override public void run() throws Exception {
        DecompInterface d = new DecompInterface();
        DecompileOptions o = new DecompileOptions();
        o.grabFromProgram(currentProgram);
        d.setOptions(o);
        d.toggleCCode(true);
        d.toggleSyntaxTree(true);
        d.setSimplificationStyle("decompile");
        boolean ok = d.openProgram(currentProgram);
        println("openProgram=" + ok + "  msg=" + d.getLastMessage());

        for (String a : getScriptArgs()) {
            Address ad = addr(Long.decode(a));
            Function f = getFunctionContaining(ad);
            if (f == null) { try { f = createFunction(ad,null); } catch(Exception e){} }
            if (f == null) { println("### "+a+": no function"); continue; }
            println("\n################ " + f.getName() + " @ " + f.getEntryPoint());
            DecompileResults res = d.decompileFunction(f, 120, monitor);
            println("completed=" + (res!=null && res.decompileCompleted())
                   + " err=" + (res==null?"null":String.valueOf(res.getErrorMessage()))
                   + " hasDF=" + (res!=null && res.getDecompiledFunction()!=null));
            if (res!=null && res.getDecompiledFunction()!=null) {
                println(res.getDecompiledFunction().getC());
            } else if (res!=null && res.getCCodeMarkup()!=null) {
                println(res.getCCodeMarkup().toString());
            }
        }
        d.dispose();
    }
    private Address addr(long v){ return currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(v); }
}
